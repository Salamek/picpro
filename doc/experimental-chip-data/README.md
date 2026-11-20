# Experimental chip definitions

## PIC16F887

This definition corrects the device ID, memory sizes, and configuration words
from [issue #49](https://github.com/Salamek/picpro/issues/49) using
[Microchip DS41287C](https://ww1.microchip.com/downloads/en/DeviceDoc/41287C.pdf).

The firmware core, power sequence, erase mode, and timing values are carried over
from the issue's experiment. Use this definition for offline inspection and
read-only investigation. A valid ROM dump remains to be confirmed on hardware.
PicPro's current midrange protocol implementation accepts one configuration word
for programming, and this chip needs two.

To try the definition without replacing your normal chip database on Linux,
give PicPro a temporary user data directory from the repository root:

```sh
data_dir=$(mktemp -d)
mkdir -p "$data_dir/picpro/chip-data.d"
cp doc/experimental-chip-data/16f887.yml "$data_dir/picpro/chip-data.d/"
XDG_DATA_HOME="$data_dir" picpro chip_info 16f887
```
