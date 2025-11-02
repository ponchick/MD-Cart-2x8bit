# MD-Cart-2x8bit

A KiCad project for a Sega Mega Drive/Genesis cartridge PCB. Designed to use two standard 8-bit 32-pin ROMs to form a 16-bit ROM bus.

## Hardware Requirements

Most parallel ROMs in DIP-32 packages with 8-bit memory organization should work. For EEPROM/Flash chips, solder jumper pins 1-2; for EPROM chips, solder pins 2-3.

### Compatible ROM Chips

The following DIP-32 8-bit EPROM/ROM chips are compatible with this design:

| Chip Model | Capacity | Organization | Jumpers |
|------------|----------|--------------|---------|
| ST M27C1001 | 128 KB | 1 Mbit × 8 | 2-3 |
| Winbond W27C020 | 256 KB | 2 Mbit × 8 | 1-2 |
| AMIC A29040B | 512 KB | 4 Mbit × 8 | 1-2 |
| SST SST39SF040 | 512 KB | 4 Mbit × 8 | 1-2 |
| ST M27C801 | 1 MB | 8 Mbit × 8 | 2-3 |

## Scripts

### split_msb_lsb.py

Splits a 16-bit binary file into upper and lower byte files for programming into two separate 8-bit ROMs. Supports big-endian (default for Motorola 68000) and little-endian byte order.

**Requirements:** Python 3.6 or higher. Optional: `libarchive-c` for archive format support.

#### Usage

```bash
python3 scripts/split_msb_lsb.py <filename> [options]
```

#### Options

- `filename` (required)
  - Input binary file or archive (.7z, .zip, .rar) to split
  - If an archive is provided, the first file found will be processed

- `--little-endian`
  - Use little-endian byte order instead of big-endian
  - Default: big-endian (Motorola 68000 standard)

- `-f, --force`
  - Overwrite existing output files without prompting
  - Default: prompt for confirmation if output files exist

- `-o, --output PREFIX`
  - Specify output filename prefix
  - Default: uses input filename as base
  - If `PREFIX` is an existing directory, files are saved there with original filename
  - Output files are named: `<prefix>.lower.bin` and `<prefix>.upper.bin`

- `--odd-byte {skip,lower,upper,error}`
  - Action to take when input file has odd number of bytes:
    - `error` (default): Print error and exit
    - `skip`: Skip the odd byte with a warning
    - `lower`: Add the odd byte to the lower byte file
    - `upper`: Add the odd byte to the upper byte file

#### Examples

```bash
# Basic usage (big-endian)
python3 scripts/split_msb_lsb.py rom.bin

# Little-endian byte order
python3 scripts/split_msb_lsb.py rom.bin --little-endian

# Specify output prefix
python3 scripts/split_msb_lsb.py rom.bin -o output/myrom

# Process archive and force overwrite
python3 scripts/split_msb_lsb.py game.zip -f

# Handle odd byte by adding to lower file
python3 scripts/split_msb_lsb.py rom.bin --odd-byte lower
```

#### Output

The script generates two files:

- `<prefix>.lower.bin` - Contains the lower (LSB) bytes for the first ROM
- `<prefix>.upper.bin` - Contains the upper (MSB) bytes for the second ROM

#### Archive Support

Archive format support requires `libarchive-c`:

```bash
pip install libarchive-c
```

Supported archive formats: `.7z`, `.zip`, `.rar`

## License

- Hardware: CERN Open Hardware Licence Version 2 - Permissive (CERN-OHL-P)
- Software: MIT License
