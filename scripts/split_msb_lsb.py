#!/usr/bin/env python3
"""
Split binary file into upper and lower byte files.

Reads 16-bit words from input file and splits them into:
- .lower file: low (LSB) bytes
- .upper file: high (MSB) bytes
"""

import argparse
import io
import sys
from pathlib import Path
from typing import BinaryIO

# Try to import libarchive - make it optional
try:
    import libarchive
    LIBARCHIVE_AVAILABLE = True
except ImportError:
    LIBARCHIVE_AVAILABLE = False

# Constants for archive support
ALL_ARCHIVE_EXTENSIONS = {'.7z', '.zip', '.rar'}
ARCHIVE_EXTENSIONS = ALL_ARCHIVE_EXTENSIONS if LIBARCHIVE_AVAILABLE else set()


def parse_args():
    """Parse command line arguments."""
    script_name = Path(sys.argv[0]).name
    # Build supported formats string
    all_extensions = ARCHIVE_EXTENSIONS | {'.bin', ''}  # Common binary extensions
    supported_formats = ", ".join(sorted(all_extensions)) if ARCHIVE_EXTENSIONS else "binary files"
    if not LIBARCHIVE_AVAILABLE:
        format_note = f"Supported: binary files (archive support disabled - install libarchive-c for .7z, .zip, .rar)"
    else:
        format_note = f"Supported formats: {supported_formats}"
    
    parser = argparse.ArgumentParser(
        description='Splits binary file words into upper and lower byte files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f'Example: {script_name} data.bin -> data.lower.bin and data.upper.bin\n{format_note}'
    )
    parser.add_argument(
        'filename',
        type=str,
        help='Input binary file or archive to split'
    )
    parser.set_defaults(big_endian=True)
    parser.add_argument(
        '--little-endian',
        action='store_false',
        dest='big_endian',
        help='Use little-endian byte order (default: big-endian for Motorola 68000)'
    )
    parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='Overwrite existing output files without asking'
    )
    parser.add_argument(
        '-o', '--output',
        type=str,
        metavar='PREFIX',
        help='Output filename prefix (default: input filename)'
    )
    parser.add_argument(
        '--odd-byte',
        choices=['skip', 'lower', 'upper', 'error'],
        default='error',
        help='What to do with odd byte in file: error (default), skip, add to lower, or add to upper'
    )
    return parser.parse_args()


def check_input_file(filepath: Path) -> None:
    """Validate input file exists and is readable."""
    if not filepath.exists():
        print(f"Error: File '{filepath}' does not exist!", file=sys.stderr)
        sys.exit(1)
    if not filepath.is_file():
        print(f"Error: '{filepath}' is not a regular file!", file=sys.stderr)
        sys.exit(1)
    if not filepath.stat().st_size:
        print(f"Warning: File '{filepath}' is empty!", file=sys.stderr)


def generate_output_names(input_path: Path, output_prefix: str = None) -> tuple[Path, Path]:
    """
    Generate output filenames from input filename.
    
    Args:
        input_path: Path to input file (used to extract base name if no prefix)
        output_prefix: Output prefix. If it's an existing directory, files are saved there
                      with original filename. Otherwise, treated as filename prefix (path + name).
    
    Returns:
        Tuple of (lower_file_path, upper_file_path)
    """
    if output_prefix is None:
        # No prefix: use input filename, save in current directory
        base_name = input_path.stem if input_path.suffix else input_path.name
        output_dir = Path.cwd()
        # Build output filenames with .lower.bin and .upper.bin
        lo_file = output_dir / f"{base_name}.lower.bin"
        up_file = output_dir / f"{base_name}.upper.bin"
    else:
        prefix_path = Path(output_prefix)
        
        # Check if prefix exists and is a directory
        if prefix_path.exists() and prefix_path.is_dir():
            # Existing directory: save files there with input filename
            base_name = input_path.stem if input_path.suffix else input_path.name
            lo_file = prefix_path / f"{base_name}.lower.bin"
            up_file = prefix_path / f"{base_name}.upper.bin"
        else:
            # Not a directory or doesn't exist: treat as filename prefix
            # Use the prefix as-is (can be absolute or relative path + name)
            if prefix_path.is_absolute():
                # Absolute path: use parent directory and name
                output_dir = prefix_path.parent
                base_name = prefix_path.stem if prefix_path.suffix else prefix_path.name
            else:
                # Relative path: resolve relative to current directory
                resolved_path = (Path.cwd() / prefix_path).resolve()
                output_dir = resolved_path.parent
                base_name = resolved_path.stem if resolved_path.suffix else resolved_path.name
            
            lo_file = output_dir / f"{base_name}.lower.bin"
            up_file = output_dir / f"{base_name}.upper.bin"
    
    return lo_file, up_file


def check_output_files(lo_file: Path, up_file: Path, force: bool) -> bool:
    """Check if output files exist and prompt for overwrite if needed."""
    if lo_file.exists() or up_file.exists():
        if force:
            return True
        
        existing = []
        if lo_file.exists():
            existing.append(str(lo_file))
        if up_file.exists():
            existing.append(str(up_file))
        
        # Check if we're in an interactive terminal
        if not sys.stdin.isatty():
            # Not interactive, print error and exit
            print(f"Error: Output file(s) already exist: {', '.join(existing)}", file=sys.stderr)
            print("Use --force to overwrite existing files", file=sys.stderr)
            return False
        
        # Interactive mode - ask for confirmation
        print(f"Warning: Output file(s) already exist: {', '.join(existing)}", file=sys.stderr)
        try:
            response = input("Overwrite? [Y/n] ").strip()
        except KeyboardInterrupt:
            # User pressed Ctrl-C, exit gracefully
            print(file=sys.stderr)  # New line after ^C
            sys.exit(130)  # Standard exit code for SIGINT
        
        if response and response[0].lower() != 'y':
            print("Operation cancelled.", file=sys.stderr)
            return False
    return True


def split_file_from_stream(word_file: BinaryIO, lo_file: Path, up_file: Path, 
                           big_endian: bool, odd_byte_action: str, 
                           buffer_size: int = 65536) -> tuple[int, bool, int]:
    """
    Split input stream into upper and lower byte files using buffered I/O.
    
    Args:
        word_file: Binary file-like object to read from
        lo_file: Path to output file for lower bytes
        up_file: Path to output file for upper bytes
        big_endian: Byte order flag
        odd_byte_action: Action for odd byte ('error', 'skip', 'lower', 'upper')
        buffer_size: Buffer size for I/O operations
    
    Returns:
        tuple: (bytes_written, had_odd_byte, odd_byte_value) 
               where odd_byte_value is -1 if no odd byte or action is 'skip'
    """
    try:
        with open(lo_file, 'wb', buffering=buffer_size) as lo_byte_file, \
             open(up_file, 'wb', buffering=buffer_size) as up_byte_file:
            
            bytes_written = 0
            odd_byte_value = -1
            remainder = b''
            
            # Read in larger chunks for better performance
            while True:
                # Prepend remainder from previous chunk
                read_data = word_file.read(buffer_size)
                
                if not read_data:
                    # EOF reached, process any remaining remainder
                    break
                
                chunk = remainder + read_data
                remainder = b''
                
                # Process complete word pairs
                chunk_len = len(chunk)
                word_pairs = chunk_len // 2
                
                if word_pairs > 0:
                    # Use memoryview for efficient slicing
                    data = memoryview(chunk[:word_pairs * 2])
                    
                    if big_endian:
                        # Big-endian: even bytes (0,2,4...) -> upper, odd bytes (1,3,5...) -> lower
                        # Slice efficiently: [::2] for even indices, [1::2] for odd indices
                        up_bytes = bytes(data[::2])
                        lo_bytes = bytes(data[1::2])
                    else:
                        # Little-endian: even bytes (0,2,4...) -> lower, odd bytes (1,3,5...) -> upper
                        lo_bytes = bytes(data[::2])
                        up_bytes = bytes(data[1::2])
                    
                    # Write buffered chunks
                    lo_byte_file.write(lo_bytes)
                    up_byte_file.write(up_bytes)
                    
                    bytes_written += word_pairs
                    
                    # Keep remainder (last byte if odd length)
                    remainder = chunk[word_pairs * 2:]
                else:
                    # Less than 2 bytes in chunk, keep as remainder for next iteration
                    remainder = chunk
                    # Continue reading to see if more data comes
            
            # Handle remainder (odd byte)
            if remainder:
                odd_byte_value = remainder[0]
                
                if odd_byte_action == 'error':
                    print(f"Error: File has odd number of bytes. Last byte: 0x{odd_byte_value:02x}", 
                          file=sys.stderr)
                    print("Use --odd-byte to specify handling (skip, lower, upper)", file=sys.stderr)
                    sys.exit(1)
                elif odd_byte_action == 'skip':
                    print(f"Warning: File has odd number of bytes. Last byte 0x{odd_byte_value:02x} will be skipped.", 
                          file=sys.stderr)
                    odd_byte_value = -1  # Mark as skipped for return value
                elif odd_byte_action == 'lower':
                    print(f"Info: File has odd number of bytes. Last byte 0x{odd_byte_value:02x} will be added to lower file.", 
                          file=sys.stderr)
                    lo_byte_file.write(remainder)
                elif odd_byte_action == 'upper':
                    print(f"Info: File has odd number of bytes. Last byte 0x{odd_byte_value:02x} will be added to upper file.", 
                          file=sys.stderr)
                    up_byte_file.write(remainder)
            
            return bytes_written, odd_byte_value >= 0, odd_byte_value if odd_byte_value >= 0 else -1
            
    except IOError as e:
        print(f"Error reading/writing files: {e}", file=sys.stderr)
        sys.exit(1)


def split_file(input_path: Path, lo_file: Path, up_file: Path, big_endian: bool, 
               odd_byte_action: str, buffer_size: int = 65536) -> tuple[int, bool, int]:
    """
    Split input file into upper and lower byte files using buffered I/O.
    
    Returns:
        tuple: (bytes_written, had_odd_byte, odd_byte_value) 
               where odd_byte_value is -1 if no odd byte or action is 'skip'
    """
    with open(input_path, 'rb', buffering=buffer_size) as word_file:
        return split_file_from_stream(word_file, lo_file, up_file, big_endian, 
                                     odd_byte_action, buffer_size)


def get_first_file_from_archive(filename: str) -> str:
    """
    Get the name of the first file in an archive.
    
    Args:
        filename: Path to the archive
        
    Returns:
        Name of the first file in the archive
        
    Raises:
        SystemExit: If libarchive not available or no files found
    """
    if not LIBARCHIVE_AVAILABLE:
        print("Error: libarchive not available - archive support disabled", file=sys.stderr)
        print("For archive format support, install libarchive-c: pip install libarchive-c", file=sys.stderr)
        sys.exit(1)
    
    with open(filename, 'rb') as f:
        with libarchive.fd_reader(f.fileno()) as archive:
            files_in_archive = []
            for entry in archive:
                if entry.isfile:
                    files_in_archive.append(entry.name)
            
            if not files_in_archive:
                print("Error: No files found in archive", file=sys.stderr)
                sys.exit(1)
            
            # Warn if multiple files found
            if len(files_in_archive) > 1:
                print(f"Warning: Found {len(files_in_archive)} files in archive:", file=sys.stderr)
                for file_name in files_in_archive:
                    print(f"  - {file_name}", file=sys.stderr)
                print(f"Processing only the first file: {files_in_archive[0]}", file=sys.stderr)
                print(file=sys.stderr)  # Empty line for readability
            
            return files_in_archive[0]


def process_archive(filename: str, lo_file: Path, up_file: Path, 
                   big_endian: bool, odd_byte_action: str, 
                   buffer_size: int = 65536) -> tuple[int, bool, int]:
    """
    Process an archive (.7z, .zip, or .rar) and split the first file found.
    
    Args:
        filename: Path to the archive
        lo_file: Path to output file for lower bytes
        up_file: Path to output file for upper bytes
        big_endian: Byte order flag
        odd_byte_action: Action for odd byte ('error', 'skip', 'lower', 'upper')
        buffer_size: Buffer size for I/O operations
        
    Returns:
        tuple: (bytes_written, had_odd_byte, odd_byte_value) 
               where odd_byte_value is -1 if no odd byte or action is 'skip'
               
    Raises:
        SystemExit: If libarchive not available or archive processing fails
    """
    if not LIBARCHIVE_AVAILABLE:
        print("Error: libarchive not available - archive support disabled", file=sys.stderr)
        print("For archive format support, install libarchive-c: pip install libarchive-c", file=sys.stderr)
        sys.exit(1)
    
    # Extract the first file
    with open(filename, 'rb') as f:
        with libarchive.fd_reader(f.fileno()) as archive:
            for entry in archive:
                if entry.isfile:
                    # Read all data from the entry efficiently
                    blocks = []
                    for block in entry.get_blocks():
                        blocks.append(block)
                    data = b''.join(blocks)
                    
                    # Create BytesIO object and process
                    bio = io.BytesIO(data)
                    return split_file_from_stream(bio, lo_file, up_file, big_endian, 
                                                 odd_byte_action, buffer_size)
    
    # Should not reach here
    print("Error: Failed to extract file from archive", file=sys.stderr)
    sys.exit(1)


def main():
    """Main function."""
    args = parse_args()
    
    input_path = Path(args.filename)
    
    # Check if file exists and is readable
    if not input_path.exists():
        print(f"Error: File '{input_path}' does not exist!", file=sys.stderr)
        sys.exit(1)
    if not input_path.is_file():
        print(f"Error: '{input_path}' is not a regular file!", file=sys.stderr)
        sys.exit(1)
    
    # Determine if input is an archive
    file_ext = input_path.suffix.lower()
    is_archive = file_ext in ALL_ARCHIVE_EXTENSIONS
    
    # For archives, use first file name from archive as base; for regular files, use file itself
    if is_archive:
        if not LIBARCHIVE_AVAILABLE:
            print(f"Error: Unsupported file extension: {file_ext}", file=sys.stderr)
            print("For archive format support, install libarchive-c: pip install libarchive-c", file=sys.stderr)
            sys.exit(1)
        # Get first file name from archive and use it as base for output
        first_file_name = get_first_file_from_archive(args.filename)
        # Use the directory of the archive and the name of the file from archive
        base_path = input_path.parent / Path(first_file_name).name
    else:
        base_path = input_path
        check_input_file(input_path)
    
    lo_file, up_file = generate_output_names(base_path, args.output)
    
    if not check_output_files(lo_file, up_file, args.force):
        sys.exit(0)
    
    # Calculate optimal buffer size: 512KB or file size if smaller
    if is_archive:
        # For archives, use default buffer size (we don't know extracted file size beforehand)
        buffer_size = 512 * 1024
    else:
        file_size = input_path.stat().st_size
        buffer_size = min(512 * 1024, file_size) if file_size > 0 else 512 * 1024
    
    try:
        if is_archive:
            bytes_written, had_odd_byte, odd_byte_value = process_archive(
                args.filename, lo_file, up_file, args.big_endian, 
                args.odd_byte, buffer_size
            )
        else:
            bytes_written, had_odd_byte, odd_byte_value = split_file(
                input_path, lo_file, up_file, args.big_endian, 
                args.odd_byte, buffer_size
            )
    except KeyboardInterrupt:
        # User pressed Ctrl-C, exit gracefully
        print(file=sys.stderr)  # New line after ^C
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    if bytes_written == 0 and not had_odd_byte:
        print("Warning: No data was written (input file may be empty or too small).", file=sys.stderr)
    
    # Calculate file sizes for accurate reporting
    lo_size = lo_file.stat().st_size
    up_size = up_file.stat().st_size
    
    print(f"File split successfully:")
    print(f"  Lower bytes: '{lo_file}' ({lo_size} bytes)")
    print(f"  Upper bytes: '{up_file}' ({up_size} bytes)")
    print(f"  Complete word pairs: {bytes_written}")
    if had_odd_byte:
        action_desc = args.odd_byte
        if args.odd_byte == 'skip':
            action_desc = 'skipped'
        print(f"  Odd byte (0x{odd_byte_value:02x}): {action_desc}")
    print(f"  Byte order: {'big-endian (Motorola 68000)' if args.big_endian else 'little-endian'}")


if __name__ == '__main__':
    main()