avis
===
a quick proof-of-concept continuous FFT over an audio input,
intended to stream matrix data to an Arduino LED matrix

Specialized output for a 32x16 pixel matrix allows data to be sent over very quickly.
The FFT amplitudes can be represented with a single hex digit for each column, making an entire frame of FFT data only 32*4 = 128 bits (!)

This allows a device running at 9600 baud to receive 75 frames per second!

Arduino-side code is WIP and will be uploaded soon.
