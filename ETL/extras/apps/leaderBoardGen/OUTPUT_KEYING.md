# Output and Clear modes

Device 0 and HD 1080i50 remain the preferred selections when supported.

## Normal video

Clear sends black and keeps SDI running. Use a switcher cut or transition to
return to the camera. A single ordinary SDI video signal has no transparent mode.

## Chroma green / blue

Configure the receiving switcher's chroma key with the matching colour and put
the camera underneath that keyed input. Confirm the setup before starting.
Standby and Clear send solid RGB green (0,255,0) or blue (0,0,255), converted by
the existing SDI pipeline. Calibrate the switcher's key using that actual signal.
Push On Air sends the normal graphic. The switcher may also remove matching
colours inside graphics, photographs or videos. This is not alpha key/fill.

The browser monitors the outgoing software signal, not the switcher composite.
Without receiver keying, Clear displays a coloured screen, not the camera.

## External key/fill and internal keying

These options are intentionally disabled pending verified hardware support and
wiring. External key/fill needs separate synchronized key and fill signals and a
configured receiver keyer. Internal keying composites a video input in supported
DeckLink hardware. Neither is implemented by the current RGB/YUV output path.
Changing DeckLink duplex mode can change connector assignments. Do not enable it
blindly or assume the attached switcher can be autodetected over SDI.

Reference: https://gstreamer.freedesktop.org/documentation/decklink/decklinkvideosink.html

Before production, verify camera, Push, Clear, format, colours and signal continuity
on the actual switcher. Software tests do not verify physical SDI behaviour.
