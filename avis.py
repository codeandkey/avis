#!/bin/env python

"""
    avis.py

    audio visualizer / matrix controller
"""

import math
import numpy
import pygame
import queue
import random
import serial
import sounddevice as sd
import time

# serial interface
local_device = serial.Serial('/dev/ttyACM1', 115200, timeout=5)

# application configuration
led_width         = 32
led_height        = 16
framerate         = 60
display_scale     = 20
samples_per_frame = 512

# audio frame history
hist_len = 128
min_buf  = [0] * hist_len
max_buf  = [0] * hist_len
hist_idx = 0

# dropoff states
dropoffs = [0] * led_width

# matrix state
current_levels = [0] * led_width

# display state
display = 0

# draw a single bar or point
def render_column(x):
    # update dropoff for this bucket
    dropoffs[x] = max(dropoffs[x] - 0.25, current_levels[x] + 0.5)

    if dropoffs[x] < 0:
        dropoffs[x] = 0
    if dropoffs[x] >= led_height:
        dropoffs[x] = led_height - 1

    # helper to invert y values vertically
    def normalize_y(y):
        return led_height - (y + 1)

    # don't render empty levels cause they're ugly
    if current_levels[x] > 0:
        pygame.draw.rect(display, (255, 255, 255), [x * display_scale, normalize_y(current_levels[x]) * display_scale, display_scale, current_levels[x] * display_scale])

    # blit the dropoff point
    pygame.draw.rect(display, (130, 30, 255), [x * display_scale, normalize_y(dropoffs[x]) * display_scale, display_scale, display_scale / 2])

# process a completed frame
def output_matrix():
    display.fill((0, 0, 0))

    for x in range(0, led_width):
        render_column(x)

    pygame.display.flip()

    for evt in pygame.event.get():
        if evt.type == pygame.QUIT:
            return False
        if evt.type == pygame.KEYDOWN:
            if evt.key == pygame.K_ESCAPE:
                return False

    return True

# upload matrix over serial port
def upload_matrix():
    for i in range(0, int(led_width)):
        local_device.write(current_levels[i].to_bytes(1, byteorder='big'))
    #local_device.write(b'\xFF')

# compute non-normalized fft coefficient amplitudes, crunched into led_width buckets
def compute_amplitudes(frame):
    # get raw fft
    fft = numpy.fft.rfft(frame)

    # slice in half, grab the first bits
    fft = fft[:len(fft)//2]

    # crunch down to led_width buckets
    out = [0] * led_width
    bucket_width = int(len(fft) / led_width)

    for i in range(0, led_width):
        for j in range(0, bucket_width):
            val = fft[i * bucket_width + j]
            # grab amplitude from complex coefficient
            out[i] += float(math.sqrt(math.pow(val.real, 2) + math.pow(val.imag, 2)))
        out[i] /= bucket_width

    return out

# normalize amplitudes based on history (in-place)
def normalize_amplitudes(amp):
    global hist_idx

    cur_min = amp[0]
    cur_max = amp[0]

    # compute min/max for amp frame
    for i in range(0, len(amp)):
        if amp[i] < cur_min:
            cur_min = amp[i]
        if amp[i] > cur_max:
            cur_max = amp[i]

    # push min/max to circular histbuf
    min_buf[hist_idx] = cur_min
    max_buf[hist_idx] = cur_max

    hist_idx += 1

    if hist_idx >= hist_len:
        hist_idx = 0

    # get new hist min/max
    for i in range(0, hist_len):
        if min_buf[i] < cur_min:
            cur_min = min_buf[i]
        if max_buf[i] > cur_max:
            cur_max = max_buf[i]

    # don't allow zero len ranges
    if cur_max == cur_min:
        cur_max = cur_min + 1

    # scale amplitudes on new history
    for i in range(0, len(amp)):
        amp[i] = (amp[i] - cur_min) / (cur_max - cur_min)

# generate new pixel matrix from normalized amplitudes
def update_matrix_from_amplitudes(amps):
    # these should all be between 0 and 1
    for x in range(0, led_width):
        current_levels[x] = int(amps[x] * led_height)

# start visualizing audio
def start_vis():
    global led_matrix

    # audio data queue for threadsafety
    q = queue.Queue()

    # audio thread data callback
    def callback(data, frames, time, status):
        if status:
            print(status)
        q.put(data.copy())

    print('devices:')
    print(sd.query_devices())

    with sd.InputStream(samplerate=44100, channels=1, blocksize=samples_per_frame,  callback=callback):
        while output_matrix():
            # grab the most recent audio frame
            cur_frame = None

            try:
                while True:
                    cur_frame = q.get_nowait()
            except queue.Empty:
                if cur_frame is None:
                    cur_frame = q.get()

            # compute the fft amplitudes
            amps = compute_amplitudes(cur_frame)
            normalize_amplitudes(amps)
            update_matrix_from_amplitudes(amps)

            # send matrix data to device
            upload_matrix()

            time.sleep(1/framerate)

# entry point
def start():
    global display

    # initialize display
    display = pygame.display.set_mode((led_width * display_scale, led_height * display_scale))

    start_vis()

if __name__ == '__main__':
    start()
