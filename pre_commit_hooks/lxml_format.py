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


def beautify(filename: str, width: int, retries: int) -> None:
  space = ' '
  style = 'space'

  if width <= 0:
    # Acquire properties from .editorconfig
    try:
      properties = get_properties(os.path.abspath(filename))

      # Resolve indentation and its size from editor config
      if 'indent_style' in properties:
        style = properties['indent_style']
        if style == 'tab':
          width = 1
          space = '\t'
          logging.debug(f'Indentation set to tabs via editorconfig')
      if style == 'space':
        if 'indent_size' in properties:
          width = int(properties['indent_size'])
          space = ' '
          logging.debug(f'Indentation set to {width} via editorconfig')
      if width <= 0:
        width = INDENT
        logging.warning(f'No indentation information in editorconfig, defaulting to {width}')
    except EditorConfigError:
      width = INDENT
      logging.warning(f"Error getting EditorConfig properties. Defaulting indentation to {width}.", exc_info=True)
  else:
    logging.debug(f'Indentation set to {width} via CLI')

  # Read file content, binary mode
  with open(filename, 'rb') as f:
    content = f.read()

  # Pretty print the content
  original = content
  for _ in range(retries):
    xml = pretty_print(original, space=space, width=width)
    if xml == original:
      break
    original = xml

  # Write the content back to the file if it has changed
  if xml == content:
    logging.debug(f'No change: {filename}')
  else:
    logging.info(f'Formatted: {filename}')
    with open(filename, "wb") as f:
      f.write(xml)

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
    for filename in args.filenames:
      beautify(filename, args.width, args.retries)
    return 0
  except Exception as e:
    logging.error(e)
    return 1

if __name__ == '__main__':
  raise SystemExit(main())
