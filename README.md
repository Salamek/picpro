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

## Usage

```text
Command details:
    program             Program PIC chip.
    verify              Verify PIC flash.
    dump                Dump PIC data as binary.
    erase               Erase PIC.
    chipinfo            Prints chipinfo as JSON in terminal.
    hexinfo             Prints information about hexfile.

Usage:
    picpro program -p PORT -i HEX_FILE -t PIC_TYPE [--id=PIC_ID] [--fuse=FUSE_NAME:FUSE_VALUE...] [--icsp]
    picpro verify -p PORT -i HEX_FILE -t PIC_TYPE [--icsp]
    picpro erase -p PORT -t PIC_TYPE [--icsp]
    picpro dump <mem_type> -p PORT -o HEX_FILE -t PIC_TYPE [--icsp] [--binary]
    picpro chipinfo [<PIC_TYPE>]
    picpro hexinfo <HEX_FILE> <PIC_TYPE>
    picpro (-h | --help)


Options:
    --icsp                           Enable ISCP programming.
    --fuse=FUSE_NAME:FUSE_VALUE      Set fuse value directly.
    --id=PIC_ID                      Set PIC id to be programmed in pic.
    -p PORT --port=PORT              Set serial port where programmer is connected.
    -t PIC_TYPE --pic_type=PIC_TYPE  Pic type you are programming/reading.
    -i HEX_FILE --hex_file=HEX_FILE  Hex file to flash or to read.
    -o HEX_FILE --hex_file=HEX_FILE  Hex file to write.
    --binary                         Input/Output file is in binary.

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
