from __future__ import annotations

import argparse
import sys
import os
import logging
import re

from typing import Sequence
from lxml import etree
from editorconfig import get_properties, EditorConfigError

INDENT = 2
RETRIES = 5
ENV_PREFIX = 'PRE_COMMIT_HOOK_LXML_FORMAT_'

def pretty_print(content: bytes, space: str, indent: int) -> bytes:
  """
  Pretty prints an XML content with specified indentation. Results are per the
  lxml tostring method, with pretty_print=True. In general, this will add
  line endings, fix indentation, cleanup tags and add an XML declaration.

  Args:
    content (bytes): The XML content to be pretty printed.
    space (str): The string used for indentation.
    indent (int): The number of spaces for each indentation level.

  Returns:
    bytes: The pretty printed XML content.
  """
  parser = etree.XMLParser(
                  remove_blank_text=False,
                  recover=True,
                  strip_cdata=False)
  tree = etree.XML(content, parser=parser).getroottree()
  etree.indent(tree, space=space * indent)
  return etree.tostring(tree,
              pretty_print=True,
              encoding=tree.docinfo.encoding,
              xml_declaration=True)


def get_indent_from_editorconfig(filename: str) -> tuple[int, str]:
  """
  Get the indent style and size from the EditorConfig properties of a file.

  Args:
    filename (str): The path of the file.

  Returns:
    tuple[int, str]: A tuple containing the indent size and style.
      The first element is the indent size, and the second element is the indent style.
  """
  try:
    properties = get_properties(os.path.abspath(filename))
    if 'indent_style' in properties:
      style = properties['indent_style']
      if style == 'tab':
        return 1, '\t'
      if 'indent_size' in properties and style == 'space':
        return int(properties['indent_size']), ' '
  except EditorConfigError:
    logging.warning("Error getting EditorConfig properties.", exc_info=True)
  except ValueError:
    logging.warning("Error parsing indent_size in editorconfig.", exc_info=True)
  return INDENT, ' '


def beautify(
      filename: str,
      indent: int = INDENT,
      retries: int = RETRIES,
      write: bool = False,
      endings: str = 'auto') -> bool:
  """
  Beautifies, e.g. gently reformat the XML content of a file. Changes can be
  written back to the file.

  Args:
    filename (str): The path of the file to be beautified.
    indent (int, optional): The number of spaces to use for indentation. Defaults to INDENT.
    retries (int, optional): The number of retries to attempt for pretty printing. Defaults to RETRIES.
    write (bool, optional): Flag indicating whether to write the changes to the file. Defaults to False.

  Returns:
    bool: True if the file was beautified successfully, False otherwise.
  """
  # Get the indentation indent and style from the CLI or .editorconfig
  if indent < 0:
    indent, space = get_indent_from_editorconfig(filename)
    logging.debug(f'Indentation set to {indent} spaces via editorconfig or default.')
  else:
    space = ' '
    logging.debug(f'Indentation set to {indent} via CLI')

  # Read file content, binary mode into original variable
  try:
    with open(filename, 'rb') as f:
      original = f.read()
  except Exception as e:
    logging.error(f'Failed to read file: {filename}: {e}')
    return False

  # Pretty print the content until it has not changed between two iterations.
  content = original
  for _ in range(retries):
    xml = pretty_print(original, space=space, indent=indent)
    if xml == content:
      break
    content = xml

  # Convert line endings, if relevant. Detect from original content if
  # necessary. Note: the output of pretty_print is always using unix line
  # endings.
  if endings == 'windows':
    logging.debug(f'Windows line endings enforced: {filename}')
    xml = xml.replace(b'\n', b'\r\n')
  elif endings == 'mac':
    logging.debug(f'Mac (classic) line endings enforced: {filename}')
    xml = xml.replace(b'\n', b'\r')
  elif endings == 'auto':
    # windows or ancient mac somewhere?
    if b'\r\n' in original:
      logging.info(f'Windows line endings detected: {filename}')
      xml = xml.replace(b'\n', b'\r\n')
    elif b'\r' in original and not b'\r\n' in original:
      logging.info(f'Mac (classic) line endings detected: {filename}')
      xml = xml.replace(b'\n', b'\r')

  # Log/return the result and write the file if the write flag is set.
  if xml == content:
    logging.debug(f'No change: {filename}')
  else:
    # Write the content back to the file if it has changed and the write flag
    # is, otherwise return a negative result (error).
    if write:
      logging.info(f'Formatted: {filename}')
      try:
        with open(filename, "wb") as f:
          f.write(xml)
      except Exception as e:
        logging.error(f'Failed to write file: {filename}: {e}')
        return False
    else:
      logging.info(f'{filename} not properly formatted. Use --write to write changes.')
      return False
  return True


def str_to_bool(s) -> bool:
  """
  Converts a string to a boolean value. The string is case-insensitive and the
  following strings will be considered as True: 'true', 'on', 'yes', '1', 't',
  'y'. Any other string will be considered as False.

  Args:
    s (str): The string to be converted.

  Returns:
    bool: The boolean value corresponding to the string.

  """
  pattern=re.compile("^\s*(true|on|yes|1|t|y)\s*$", re.IGNORECASE)
  return bool(pattern.match(s))


def main(argv: Sequence[str] | None = None) -> int:
  """
  Main function for the lxml_format script. Parses the command-line arguments,
  takes into account the environment variables, and calls the beautify function
  on each file to reformat or report upon bad formatting.

  Args:
    argv: A sequence of command-line arguments. If None, sys.argv[1:] will be used.

  Returns:
    An integer representing the exit code. 0 indicates success, while non-zero values indicate errors.
    1 is used for general errors, while 2 and above are used to communicate the number of erroneous files: the exit code minus 2.
  """
  argv = argv if argv is not None else sys.argv[1:]
  parser = argparse.ArgumentParser(prog='lxml_format', description='Prettyprint XML file with lxml')

  parser.add_argument(
    '-e', '--endings', '--line-endings',
    dest='endings',
    choices=['unix', 'windows', 'mac', 'auto'],
    default='auto',
    help='Line endings in the formatted file. Default: %(default)s)'
  )

  parser.add_argument(
    '-i', '--indent',
    dest='indent',
    type=int,
    default=-1,
    help='Number of spaces to use, overrides .editorconfig when positive. Default: %(default)s)'
  )

  parser.add_argument(
    '-l', '--log-level', '--log',
    choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
    dest='loglevel',
    default='INFO',
    help='Debug level.'
  )

  parser.add_argument(
    '-r', '--retries',
    dest='retries',
    type=int,
    default=RETRIES,
    help='Max number of retries to reach content stabilisation. Default: %(default)s)'
  )

  parser.add_argument(
    '-w', '--write',
    action='store_true',
    dest='write',
    help='Write the changes back to the file'
  )

  parser.add_argument(
    'filenames',
    nargs='*',
    help='Files to format'
  )

  args = parser.parse_args(argv)

  # Existing environment variables, if set, will have precedence. This allows to
  # bypass repository-wide settings (in pre-commit configuration YAML file) with
  # local environment settings.
  indent: int = int(os.environ.get(f'{ENV_PREFIX}INDENT', args.indent))
  retries: int = int(os.environ.get(f'{ENV_PREFIX}RETRIES', args.retries))
  loglevel= os.environ.get(f'{ENV_PREFIX}LOG_LEVEL', args.loglevel)
  write: bool = str_to_bool(os.environ.get(f'{ENV_PREFIX}WRITE', str(args.write)))
  endings= os.environ.get(f'{ENV_PREFIX}LINE_ENDINGS', args.endings).lower()

  # Setup logging
  numeric_level = getattr(logging, loglevel.upper(), None)
  if not isinstance(numeric_level, int):
    raise ValueError('Invalid log level: %s' % loglevel)
  logging.basicConfig(level=numeric_level,
                      format='[lxml_format] [%(asctime)s.%(msecs)03d] [%(levelname)s] %(message)s',
                      datefmt='%Y%m%d %H%M%S')

  # Check line endings (not only CLI argument, but also environment variable)
  if not endings in ['unix', 'windows', 'mac', 'auto']:
    logging.error(f'Invalid line endings: {endings}')
    return 1

  try:
    errors: int = 0
    # Reformat/check formatting of the files. Count the ones not properly
    # formatted.
    for filename in args.filenames:
      if not beautify(filename, indent, retries, write, endings):
        errors += 1
    # Return the number of files not properly formatted + 2. This will be
    # reported to the OS as an error and enables better reporting, as long as
    # there are less than 123 files with errors. See reserved exit codes here:
    # https://tldp.org/LDP/abs/html/exitcodes.html
    if errors > 0:
      logging.error(f'Failed to format {errors} files')
      return errors+2
    return 0
  except Exception as e:
    logging.error(e)
    return 1

if __name__ == '__main__':
  raise SystemExit(main())
