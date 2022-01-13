# picpro a kitsrus PIC CLI programmer

This is complete rewrite of kitsrus_pic_programmer into Python 3 + bunch of fixes and features.

[![Tox tests](https://github.com/Salamek/picpro/actions/workflows/python-test.yml/badge.svg)](https://github.com/Salamek/picpro/actions/workflows/python-test.yml)

## Supported kitsrus programmers
    * K128
    * K149-A
    * K149-B
    * K150 (Tested)
    
See http://www.kitsrus.com/pic.html
    

## Installation

### PIP (pip3 on some distros)

```
pip install picpro
```

### Repository
You can also use these repositories maintained by me
#### Debian and derivatives

Add repository by running these commands

```
$ wget -O- https://repository.salamek.cz/deb/salamek.gpg | sudo tee /usr/share/keyrings/salamek-archive-keyring.gpg
$ echo "deb     [signed-by=/usr/share/keyrings/salamek-archive-keyring.gpg] https://repository.salamek.cz/deb/pub all main" | sudo tee /etc/apt/sources.list.d/salamek.cz.list
```

And then you can install a package picpro

```
$ apt update && apt install picpro
```

#### Archlinux

Add repository by adding this at end of file /etc/pacman.conf

```
[salamek]
Server = https://repository.salamek.cz/arch/pub/any
SigLevel = Optional
```

and then install by running

```
$ pacman -Sy picpro
```


## Usage

```
Command details:
    program             Program PIC chip.
    verify              Verify PIC flash.
    dump                Dump PIC data as binary.

Usage:
    picpro program -p PORT -i HEX_FILE -t PIC_TYPE [--id=PIC_ID] [--fuse=FUSE_NAME:FUSE_VALUE...] [--icsp]
    picpro verify -p PORT -i HEX_FILE -t PIC_TYPE [--icsp]
    picpro dump <mem_type> -p PORT -b BIN_FILE -t PIC_TYPE [--icsp]
    picpro (-h | --help)


Options:
    --icsp                           Enable ISCP programming.
    --fuse=FUSE_NAME:FUSE_VALUE      Set fuse value directly.
    --id=PIC_ID                      Set PIC id to be programmed in pic.
    -p PORT --port=PORT              Set serial port where programmer is connected.
    -t PIC_TYPE --pic_type=PIC_TYPE  Pic type you are programming/reading.
    -i HEX_FILE --hex_file=HEX_FILE  Hex file to flash or to read.
    -b BIN_FILE --bin_file=BIN_FILE  Bin file path.

```

### Program chip

```bash
picpro program -p /dev/ttyUSB0 -i YOUR_HEX_FILE.hex -t 12F675
```

### Verify chip program

```bash
picpro verify -p /dev/ttyUSB0 -i YOUR_HEX_FILE.hex -t 12F675
```

### Dump ROM as bin file

```bash
picpro dump rom -p /dev/ttyUSB0 -b dump.rom -t 12F675
```

### Dump EEPROM as bin file

```bash
picpro dump eeprom -p /dev/ttyUSB0 -b dump.eeprom -t 12F675
```

### Program chip via ISCP

```bash
picpro program -p /dev/ttyUSB0 -i YOUR_HEX_FILE.hex -t 12F675 --icsp
```

### Program chip and override fuses provided from HEX file

```bash
picpro program -p /dev/ttyUSB0 -i YOUR_HEX_FILE.hex -t 12F675 --fuse=FUSE_NAME:FUSE_VALUE --fuse=FUSE_NAME:FUSE_VALUE
```
