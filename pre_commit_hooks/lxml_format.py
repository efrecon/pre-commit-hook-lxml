from __future__ import annotations

import argparse
import sys
import os
from lxml import etree
from editorconfig import get_properties, EditorConfigError
import logging

INDENT = 2
RETRIES = 5

def pretty_print(content: bytes, space: str, width: int) -> None:
  parser = etree.XMLParser(remove_blank_text=True)
  tree = etree.XML(content, parser=parser).getroottree()
  etree.indent(tree, space=width * space)
  return etree.tostring(tree,
                        pretty_print=True,
                        encoding=tree.docinfo.encoding,
                        xml_declaration=True)


def get_indent_from_editorconfig(filename: str) -> tuple[int, str]:
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
  return INDENT, ' '


def beautify(
            filename: str,
            width: int = INDENT,
            retries: int = RETRIES,
            write: bool = False) -> bool:
  # Get the indentation width and style from the CLI or .editorconfig
  if width < 0:
    width, space = get_indent_from_editorconfig(filename)
    logging.debug(f'Indentation set to {width} spaces via editorconfig or default.')
  else:
    space = ' '
    style = 'space'
    logging.debug(f'Indentation set to {width} via CLI')

  # Read file content, binary mode
  try:
    with open(filename, 'rb') as f:
      content = f.read()
  except Exception as e:
    logging.error(f'Failed to read file: {filename}: {e}')
    return False

  # Pretty print the content
  original = content
  for _ in range(retries):
    xml = pretty_print(original, space=space, width=width)
    if xml == original:
      break
    original = xml

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

def main(argv: Sequence[str] | None = None) -> int:
  argv = argv if argv is not None else sys.argv[1:]
  parser = argparse.ArgumentParser(prog='lxml_format', description='Prettyprint XML file with lxml')

  parser.add_argument(
    '-i', '--indent',
    dest='width',
    type=int,
    default=-1,
    help='Number of spaces to use, overrides .editorconfig when positive. Default: %(default)s)'
  )

  parser.add_argument(
    '-r', '--retries',
    dest='retries',
    type=int,
    default=RETRIES,
    help='Max number of retries to reach content stabilisation. Default: %(default)s)'
  )

  parser.add_argument(
    '-l', '--log-level', '--log',
    choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
    dest='loglevel',
    default='INFO',
    help='Debug level.'
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

  # Setup logging
  numeric_level = getattr(logging, args.loglevel.upper(), None)
  if not isinstance(numeric_level, int):
    raise ValueError('Invalid log level: %s' % args.loglevel)
  logging.basicConfig(level=numeric_level,
                      format='[lxml_format] [%(asctime)s.%(msecs)03d] [%(levelname)s] %(message)s',
                      datefmt='%Y%m%d %H%M%S')

  try:
    errors: int = 0
    # Reformat/check formatting of the files. Count the ones not properly
    # formatted.
    for filename in args.filenames:
      if not beautify(filename, args.width, args.retries, args.write):
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
