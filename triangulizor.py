#!/usr/bin/env python2.7

import argparse
from cStringIO import StringIO
import logging
import os
import re
import sys
import urllib2

import Image
import ImageDraw


def triangulize(image, tile_size):
    """Processes the given image by breaking it down into tiles of the given
    size and applying a triangular effect to each tile. Returns the processed
    image.
    """
    assert isinstance(image, Image.Image), type(image)
    assert isinstance(tile_size, int) and tile_size % 2 == 0
    logging.info('Input image size: %r', image.size)
    logging.info('Tile size: %r', tile_size)
    # Preprocess image to make sure it's at a size we can handle
    image = prep_image(image, tile_size)
    logging.info('Prepped image size: %r', image.size)
    # Get pixmap (for direct pixel access) and draw objects for the image.
    pix = image.load()
    draw = ImageDraw.Draw(image)
    for x, y in iter_tiles(image, tile_size):
        process_tile(x, y, tile_size, pix, draw, image)
    return image

def process_tile(tile_x, tile_y, tile_size, pix, draw, image):
    """Process a tile whose top left corner is at the given x and y
    coordinates.
    """
    logging.debug('Processing tile (%d, %d)', tile_x, tile_y)

    # Calculate average color for each "triangle" in the given tile
    n, e, s, w = triangle_colors(tile_x, tile_y, tile_size, pix)

    # Calculate distance between triangle pairs
    d_ne = get_color_dist(n, e)
    d_nw = get_color_dist(n, w)
    d_se = get_color_dist(s, e)
    d_sw = get_color_dist(s, w)

    # Figure out which pair is the closest, which will determine the direction
    # we'll split this tile into triangles. A 'right' split runs from top left
    # to bottom right. A 'left' split runs bottom left to top right.
    closest = sorted([d_ne, d_nw, d_se, d_sw])[0]
    if closest in (d_ne, d_sw):
        split = 'right'
    elif closest in (d_nw, d_se):
        split = 'left'

    # Figure out the average color for each side of the "split"
    if split == 'right':
        top_color = get_average_color([n, e])
        bottom_color = get_average_color([s, w])
    else:
        top_color = get_average_color([n, w])
        bottom_color = get_average_color([s, e])

    draw_triangles(tile_x, tile_y, tile_size, split, top_color, bottom_color,
                   draw)

def triangle_colors(tile_x, tile_y, tile_size, pix):
    """Extracts the average color for each triangle in the given tile. Returns
    a 4-tuple of colors for the triangles in this order: North, East, South,
    West (clockwise).
    """
    quad_size = tile_size / 2

    north = []
    for y in xrange(tile_y, tile_y + quad_size):
        x_off = y - tile_y
        for x in xrange(tile_x + x_off, tile_x + tile_size - x_off):
            north.append(pix[x,y])

    south = []
    for y in xrange(tile_y + quad_size, tile_y + tile_size):
        x_off = tile_y + tile_size - y
        for x in xrange(tile_x + x_off, tile_x + tile_size - x_off):
            south.append(pix[x,y])

    east = []
    for x in xrange(tile_x, tile_x + quad_size):
        y_off = x - tile_x
        for y in xrange(tile_y + y_off, tile_y + tile_size - y_off):
            east.append(pix[x, y])

    west = []
    for x in xrange(tile_x + quad_size, tile_x + tile_size):
        y_off = tile_x + tile_size - x
        for y in xrange(tile_y + y_off, tile_y + tile_size - y_off):
            west.append(pix[x, y])

    return map(get_average_color, [north, east, south, west])

def draw_triangles(tile_x, tile_y, tile_size, split, top_color, bottom_color,
                   draw):
    """Draws a triangle on each half of the tile with the given coordinates
    and size.
    """
    assert split in ('right', 'left')

    # The four corners of this tile
    nw = (tile_x, tile_y)
    ne = (tile_x + tile_size - 1, tile_y)
    se = (tile_x + tile_size - 1, tile_y + tile_size)
    sw = (tile_x, tile_y + tile_size)

    if split == 'left':
        # top right triangle
        draw_triangle(nw, ne, se, top_color, draw)
        # bottom left triangle
        draw_triangle(nw, sw, se, bottom_color, draw)
    else:
        # top left triangle
        draw_triangle(sw, nw, ne, top_color, draw)
        # bottom right triangle
        draw_triangle(sw, se, ne, bottom_color, draw)

def draw_triangle(a, b, c, color, draw):
    """Draws a triangle with the given vertices in the given color."""
    draw.polygon([a, b, c], fill=make_color(color))

def get_average_color(colors):
    """Calculate the average color from the list of colors, where each color
    is a 3-tuple of (r, g, b) values.
    """
    tr, tg, tb = reduce(color_reducer, colors)
    total = len(colors)
    return tr/total, tg/total, tb/total

def color_reducer((r1, g1, b1), (r2, g2, b2)):
    """Helper function used to add two colors together when averaging."""
    return r1+r2, g1+g2, b1+b2

def get_color_dist((r1, g1, b1), (r2, g2, b2)):
    """Calculates the "distance" between two colors, where the distance is
    another color whose components are the absolute values of the difference
    between each component of the input colors.
    """
    return (abs(r1-r2), abs(g1-g2), abs(b1-b2))

def make_color((r, g, b)):
    """Formats a color for use in an ImageDraw method."""
    return 'rgb(%d, %d, %d)' % (r, g, b)

def prep_image(image, tile_size):
    """Takes an image and a tile size and returns a possibly cropped version
    of the image that is evenly divisible in both dimensions by the tile size.
    """
    w, h = image.size
    x_tiles = w / tile_size # floor division
    y_tiles = h / tile_size
    new_w = x_tiles * tile_size
    new_h = y_tiles * tile_size
    if new_w == w and new_h == h:
        return image
    else:
        crop_bounds = (0, 0, new_w, new_h)
        return image.crop(crop_bounds)

def iter_tiles(image, tile_size):
    """Yields (x, y) coordinate pairs for the top left corner of each tile in
    the given image, based on the given tile size.
    """
    w, h = image.size
    for y in xrange(0, h, tile_size):
        for x in xrange(0, w, tile_size):
            yield x, y


if __name__ == '__main__':

    def path_or_url(x):
        if re.match(r'^https?://', x):
            try:
                return urllib2.urlopen(x)
            except urllib2.URLError, e:
                raise argparse.ArgumentTypeError(str(e))
        elif os.path.isfile(x):
            return open(x, 'rb')
        else:
            msg = '%r not found' % x
            raise argparse.ArgumentTypeError(msg)

    def even_int(x):
        x = int(x)
        if not x % 2 == 0:
            raise argparse.ArgumentTypeError('must be an even number')
        return x

    arg_parser = argparse.ArgumentParser(
        description='Applies a "triangular pixel" effect to an image.')
    arg_parser.add_argument(
        'infile', nargs='?', default=sys.stdin, type=path_or_url,
        help='Image to process (path or URL; defaults to STDIN)')
    arg_parser.add_argument(
        'outfile', nargs='?', default=sys.stdout,
        type=argparse.FileType('wb'),
        help='Output file (defaults to STDOUT)')
    arg_parser.add_argument(
        '-t', '--tile-size', type=even_int, default=20,
        help='Tile size (must be divisible by 2; defaults to 20)')
    arg_parser.add_argument(
        '-v', '--verbose', default=False, action='store_const', const=True,
        help='Verbose output')
    arg_parser.add_argument(
        '-vv', default=False, action='store_const', const=True,
        help='Very verbose output')
    arg_parser.add_argument(
        '-s', '--show', default=False, action='store_const', const=True,
        help='Immediately display image instead of writing to OUTFILE.')

    args = arg_parser.parse_args()

    if args.verbose or args.vv:
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG if args.vv else logging.INFO)

    # We need to buffer the input because neither sys.stdin nor urllib2
    # response objects support seek()
    inbuffer = StringIO(args.infile.read())
    try:
        image = triangulize(Image.open(inbuffer), args.tile_size)
    except KeyboardInterrupt:
        logging.info('Interrupted by user, exiting...')
        sys.exit(1)
    else:
        if args.show:
            image.show()
        else:
            image.save(args.outfile, 'png')
