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
import sounddevice as sd
import time

# application configuration
led_width  = 32
led_height = 16
framerate  = 60
display_scale = 32

# audio frame history
hist_len = 128
min_buf = [0] * hist_len
max_buf = [0] * hist_len
hist_idx = 0

# dropoff states
dropoffs = [0] * led_width

# matrix state
led_matrix = [(0, 0, 0)] * led_width * led_height

# display state
display = 0

# set a single pixel
def set_pixel(x, y, col):
    led_matrix[y * led_width + x] = col

# process a completed frame
def output_matrix():
    for y in range(0, led_height):
        base_idx = y * led_width

        for x in range(0, led_width):
            pygame.draw.rect(display, led_matrix[base_idx + x], [x * display_scale, y * display_scale, display_scale, display_scale])

    pygame.display.flip()

    for evt in pygame.event.get():
        if evt.type == pygame.QUIT:
            return False
        if evt.type == pygame.KEYDOWN:
            if evt.key == pygame.K_ESCAPE:
                return False

    return True

# flush the matrix to black
def clear_matrix():
    for i in range(0, len(led_matrix)):
        led_matrix[i] = (0, 0, 0)

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
        dropoffs[x] = min(dropoffs[x] + 0.25, (1.0 - amps[x]) * led_height)

        if dropoffs[x] >= led_height:
            dropoffs[x] = led_height - 1

        if dropoffs[x] < 0:
            dropoffs[x] = 0

        for y in range(0, int(amps[x] * led_height)):
            set_pixel(x, led_height - (y + 1), (255, 255, 255))

        # also render dropoff point
        set_pixel(x, int(dropoffs[x]), (0, 120, 255))

# synchronous, render some random data for a couple frames
def cycle_random():
    global led_matrix
    time_sec = 2

    for i in range(0, framerate * time_sec):
        # fill matrix with random stuffs
        for x in range(0, led_width * led_height):
            led_matrix[x] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

        if not output_matrix():
            break

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

    with sd.InputStream(samplerate=44100, channels=1, blocksize=256,  callback=callback):
        while output_matrix():
            # grab the most recent audio frame
            cur_frame = None

            try:
                while True:
                    cur_frame = q.get_nowait()
            except queue.Empty:
                if cur_frame is None:
                    cur_frame = q.get()

            # wipe the matrix
            clear_matrix()

            # compute the fft amplitudes
            amps = compute_amplitudes(cur_frame)
            normalize_amplitudes(amps)
            update_matrix_from_amplitudes(amps)

# entry point
def start():
    global display

    # initialize display
    display = pygame.display.set_mode((led_width * display_scale, led_height * display_scale))

    start_vis()

if __name__ == '__main__':
    start()
