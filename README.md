# picpro a kitsrus PIC CLI programmer

This is complete rewrite of kitsrus_pic_programmer into Python 3 + bunch of fixes and features.

[![Tox tests](https://github.com/Salamek/picpro/actions/workflows/python-test.yml/badge.svg)](https://github.com/Salamek/picpro/actions/workflows/python-test.yml)

## Supported kitsrus programmers

* K128
* K149 version A to F
* K150 (Tested)
* K182

**Note:** The programmer must have the latest firmware version, which utilizes the P18A protocol. Firmware versions using older protocols (P018, P016, P014, or earlier) are not supported.

See <https://www.kitsrus.com/pic.html>.

## Installation

### PIP (pip3 on some distros)

```bash
pip install picpro
```

### Repository

You can also use these repositories maintained by me

#### Debian and derivatives

Add repository by running these commands

```bash
wget -O- https://repository.salamek.cz/deb/salamek.gpg | sudo tee /usr/share/keyrings/salamek-archive-keyring.gpg
echo "deb     [signed-by=/usr/share/keyrings/salamek-archive-keyring.gpg] https://repository.salamek.cz/deb/pub all main" | sudo tee /etc/apt/sources.list.d/salamek.cz.list
```

And then you can install a package picpro

```bash
apt update && apt install picpro
```

#### Archlinux

Add repository by adding this at end of file `/etc/pacman.conf`

```bash
[salamek]
Server = https://repository.salamek.cz/arch/pub/any
SigLevel = Optional
```

and then install by running

```bash
pacman -Sy picpro
```

### Running with pkgx (alternative)

You can also run picpro with [pkgx](https://github.com/pkgxdev/pkgx) without installing it:

```bash
pkgx picpro
```

## Desktop GUI

The desktop interface is distributed separately as `picpro-gui` [picpro-gui](https://github.com/Salamek/picpro-gui).
It uses the PicPro application API described below.

## Application API

`PicPro` provides synchronous workflows without importing the CLI, printing,
installing signal handlers, or selecting process exit codes:

```python
from pathlib import Path

from picpro.PicPro import PicPro, StageEvent, Target


def handle_event(event):
    if isinstance(event, StageEvent):
        print(event.stage.value)  # Replace with CLI formatting or a GUI signal.


service = PicPro(on_event=handle_event)
target = Target(port="/dev/ttyUSB0", chip_name="12f675", icsp=True)
result = service.program(target, Path("firmware.hex"))
if not result.success:
    # The caller decides how to present verification failure.
    pass
```

The service also exposes `verify`, `erase`, `read_memory`, `read_config`,
`programmer_info`, `list_chips`, `get_chip`, `inspect_hex`, `decode_fuses`, and
`migrate_chip_data`. Memory reads return device bytes; output file formats belong
to the interface. Verification returns a `VerificationResult` with ROM and
optional EEPROM outcomes. Operational failures propagate as exceptions.

Callbacks receive `StageEvent`, `ChipConfigEvent`, or `VerificationEvent` on the
calling thread. Configuration events contain snapshots; verification events
include expected and actual bytes. A GUI should call workflows in a worker and
marshal events onto its UI thread. Inject `chip_data` and `connection_factory`
when using custom definitions or testing without hardware.

Pass `should_cancel=cancel_event.is_set` to device workflows for cooperative
cancellation, which raises `OperationCancelledError`. Cancellation is checked
between complete commands, including before PIC18 fuse commits. Current events
report workflow stages; they do not report transfer byte counts or interrupt an
active transfer or erase command. Connections are released when workflows,
event handlers, or cancellation raise exceptions.

## Chip definitions

Normal commands use one YAML file per chip in `chip-data.d`. The first existing
chip directory is selected, in this order:

1. `chip-data.d` inside the user's picpro data directory (usually
   `~/.local/share/picpro/chip-data.d` on Linux).
2. `/usr/share/picpro/chip-data.d`.
3. `chip-data.d` next to the installed picpro Python package.
4. The bundled `picpro/data/chip-data.d` definitions.

The selected directory supplies the entire chip database. Copy the bundled YAML
files into your custom directory if you want to keep all supported chips while
editing individual definitions.

Legacy `chipdata.cid` files are no longer used by normal commands. The CID parser
and legacy database remain available for compatibility and conversion. To migrate
custom definitions into the user's YAML directory, run:

```bash
picpro chipdata_migrate /path/to/chipdata.cid
```

Use `--output=/path/to/chip-data.d` to choose another destination. Running
`picpro chipdata_migrate` without an input path searches the legacy user, system,
package-adjacent, and bundled CID locations. Conversion creates the destination
and replaces YAML files for chips found in the input database.

## Usage

The CLI uses Typer. Run `picpro --help` to list commands and
`picpro COMMAND --help` for command-specific arguments and options.
Existing command names (including underscores) and short options are preserved.

```text
Command details:
    program             Program PIC chip.
    verify              Verify PIC flash.
    dump                Dump PIC data as binary.
    erase               Erase PIC.
    chip_info           Print chip definitions as JSON.
    programmer_info     Print programmer firmware and protocol versions.
    read_chip_config    Read chip identification, calibration, and fuses.
    decode_fuses        Decode fuse words into named settings.
    chipdata_migrate    Convert legacy CID chip definitions to YAML.
    hex_info            Print information about a hex file.

Usage:
    picpro program -p PORT -i HEX_FILE -t PIC_TYPE [--id=PIC_ID] [--fuse=FUSE_NAME:FUSE_VALUE...] [--icsp]
    picpro verify -p PORT -i HEX_FILE -t PIC_TYPE [--icsp]
    picpro erase -p PORT -t PIC_TYPE [--icsp]
    picpro dump <mem_type> -p PORT -o HEX_FILE -t PIC_TYPE [--icsp] [--binary]
    picpro chip_info [<PIC_TYPE>]
    picpro hex_info <HEX_FILE> <PIC_TYPE>
    picpro programmer_info -p PORT
    picpro read_chip_config -p PORT -t PIC_TYPE [--icsp]
    picpro decode_fuses <fuses> -t PIC_TYPE
    picpro chipdata_migrate [<CID_FILE>] [--output=OUTPUT_DIR]
    picpro (-h | --help)
    picpro (-v | --version)


Options:
    --icsp                           Enable ISCP programming.
    --fuse=FUSE_NAME:FUSE_VALUE      Set fuse value directly.
    --id=PIC_ID                      Set PIC id to be programmed in pic.
    -p PORT --port=PORT              Set serial port where programmer is connected.
    -t PIC_TYPE --pic_type=PIC_TYPE  Pic type you are programming/reading.
    -i HEX_FILE --hex_file=HEX_FILE  Hex file to flash or to read.
    -o HEX_FILE --hex_file=HEX_FILE  Hex file to write.
    --binary                         Input/Output file is in binary.
    -v --version                     Display version info

```

### Example: Program chip

```bash
picpro program -p /dev/ttyUSB0 -i YOUR_HEX_FILE.hex -t 12F675
```

### Example: Verify chip program

```bash
picpro verify -p /dev/ttyUSB0 -i YOUR_HEX_FILE.hex -t 12F675
```

### Example: Dump ROM as hex file

```bash
picpro dump rom -p /dev/ttyUSB0 -o rom.hex -t 12F675
```

### Example: Dump EEPROM as hex file

```bash
picpro dump eeprom -p /dev/ttyUSB0 -o eeprom.hex -t 12F675
```

### Example: Back up all programmable regions

```bash
picpro dump all -p /dev/ttyUSB0 -o backup.hex -t 12F675
```

This reads ROM, EEPROM where present, user ID and configuration words in one
session and places them at their firmware HEX addresses. The backup includes
only data the programmer can read. It uses Intel HEX and cannot be combined
with `--binary`. Read protection and device-specific write support still apply
when reading or restoring a chip.

### Example: Dump CONFIG as hex file

```bash
picpro dump config -p /dev/ttyUSB0 -o config.hex -t 12F675
```

### Example: Program chip via ISCP

```bash
picpro program -p /dev/ttyUSB0 -i YOUR_HEX_FILE.hex -t 12F675 --icsp
```

### Example: Program chip and override fuses provided from HEX file

```bash
picpro program -p /dev/ttyUSB0 -i YOUR_HEX_FILE.hex -t 12F675 --fuse=FUSE_NAME:FUSE_VALUE --fuse=FUSE_NAME:FUSE_VALUE
```

## Enable serial port access

To allow the user to access the serial ports (for some distros), run the following command:

```bash
sudo usermod -a -G dialout $USER
```
