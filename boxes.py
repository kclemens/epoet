import math
import logging
import random
import json
import gzip


class Box(object):
    def __init__(self, min_lon=-180.0, min_lat=-90.0, max_lon=180.0, max_lat=90.0):
        self.max_lon = max_lon
        self.max_lat = max_lat
        self.min_lon = min_lon
        self.min_lat = min_lat

    def __repr__(self):
        return 'Box {},{}  {},{}'.format(self.min_lat, self.min_lon, self.max_lat, self.max_lon)

    def to_static_view(self):
        return 'http://maps.google.com/maps/api/staticmap?size=500x300&sensor=false&path=color:0x00000000|weight:5|fillcolor:0xFFFF0033|{},{}|{},{}|{},{}|{},{}'.format(
            self.min_lat, self.min_lon,
            self.max_lat, self.min_lon,
            self.max_lat, self.max_lon,
            self.min_lat, self.max_lon,
        )

    def width_and_height_in_m(self):
        height = (self.max_lat - self.min_lat) * (20005000 / 180.0)
        width = (self.max_lon - self.min_lon) * (40075000/ 360.0)

        return width, height

    def sub_box_index(self, lat, lon, box_count):
        q = math.sqrt(box_count)

        assert q == math.floor(q)
        assert self.min_lat <= lat < self.max_lat
        assert self.min_lon <= lon < self.max_lon

        ix = math.floor((q * (lat - self.min_lat)) / (self.max_lat - self.min_lat))
        iy = math.floor((q * (lon - self.min_lon)) / (self.max_lon - self.min_lon))

        return int(q*ix + iy)

    def sub_box(self, box_index, box_count):
        q = math.sqrt(box_count)

        assert q == math.floor(q)

        ix = math.floor(box_index / q)
        iy = box_index - ix * q

        assert ix < q and iy < q

        x_width = (self.max_lat - self.min_lat) / q
        y_width = (self.max_lon - self.min_lon) / q

        return Box(
            self.min_lon + y_width * iy,
            self.min_lat + x_width * ix,
            self.min_lon + y_width * (iy + 1),
            self.min_lat + x_width * (ix + 1)
        )

    def centroid(self):
        center_lat = self.min_lat + ((self.max_lat - self.min_lat) / 2.0)
        center_on = self.min_lon + ((self.max_lon - self.min_lon) / 2.0)
        return center_lat, center_on

class BoxIndex(object):
    def __init__(self, options, iterations=2, outer_box=Box()):
        def reduce_to_quad_length(collection):
            collection = list(collection)
            max_count = int(math.pow(math.floor(math.sqrt(len(collection))), 2))
            return collection[:max_count]

        self.line_term_options = map(reduce_to_quad_length, options)
        self.iterations = iterations
        self.outer_box = outer_box

        outer_width, outer_height = self.outer_box.width_and_height_in_m()
        inner_box_count = map(len, self.line_term_options)
        inner_box_count = reduce(lambda x,y: x * y, inner_box_count, 1)
        inner_box_count = math.pow(inner_box_count, iterations)
        inner_box_count = math.sqrt(inner_box_count)
        inner_width, inner_height = outer_width / inner_box_count, outer_height / inner_box_count
        # inner box count:
        # product of possible options for every term on a line
        # to the power of lines (iterations) specified
        # square root to get the number of boxes on a line

        self.accuracy = math.sqrt(inner_width * inner_width + inner_height * inner_height) / 2

        logging.info('configured a box index for %s', self.outer_box)
        logging.info('with %.2fm * %.2fm max tile size (%.2fm accuracy)', inner_width, inner_height, self.accuracy)

    def to_box_name(self, lat, lon):
        box = self.outer_box
        name = list()

        logging.debug('computing box name for (%.2f, %.2f) and %s', lat, lon, box)

        for _ in xrange(self.iterations):
            for terms in self.line_term_options:
                count = len(terms)
                index = box.sub_box_index(lat, lon, count)
                box = box.sub_box(index, count)
                term = terms[index]
                name.append(term)
                logging.debug('sub box index %d of %d boxes with name %s and %s', index, count, terms[index], box)

        return name

    def from_box_name(self, words):
        box = self.outer_box

        logging.debug('computing lat lon from %s and %s', words, box)

        for i, token in enumerate(words):
            line_index = i % len(self.line_term_options)
            terms = self.line_term_options[line_index]
            index = terms.index(token)
            count = len(terms)
            box = box.sub_box(index, count)

            logging.debug('for "%s" following to sub box %s with index %d of %d', token, box, index, count)

        return box

    def to_file(self, file_name='box_index.json.gz'):
        obj = {'box': {'min_x': self.outer_box.min_lat,
                       'min_y': self.outer_box.min_lon,
                       'max_x': self.outer_box.max_lat,
                       'max_y': self.outer_box.max_lon},
               'iterations': self.iterations,
               'options': self.line_term_options}
        json.dump(obj, gzip.open(file_name, 'wb'))

    @classmethod
    def from_file(cls, file_name='box_index.json.gz'):
        data = json.load(gzip.open(file_name))
        return cls(data['options'], data['iterations'], Box(data['box']['min_x'], data['box']['min_y'], data['box']['max_x'], data['box']['max_y']))

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)7s - %(message)s')

    # from random_poem import GeoPoet
    # BoxIndex(GeoPoet().generate_line_options()).to_file()
    # BoxIndex(GeoPoet(line_pattern=['^-^', '-^-'], rhyme='EY:fricative:AH:nasal').generate_line_options(), 2).to_file()
    # BoxIndex(GeoPoet(line_pattern=['^-', '-^-', '-^--'], rhyme='AA:liquid:AH:affricate:IY').generate_line_options(), 2).to_file()
    # BoxIndex(GeoPoet(line_pattern=['^--^-', '^--^-', '^--^-'], rhyme='EY:fricative:AH:nasal').generate_line_options(), 2).to_file()

    latlons = [(52.5292, 13.3882), (52.4957, 13.3634), (52.5129, 13.3201)]
    indices = [BoxIndex.from_file('rhyme_box_index.json.gz'), BoxIndex.from_file('syllables_box_index.json.gz')]

    for i, index in enumerate(indices, 1):
        print 'using box index {}'.format(i)
        for lat, lon in latlons:
            print 'encoding {},{}'.format(lat, lon)
            tokens = index.to_box_name(lat, lon)
            for i in range(len(tokens), 0, -1):
                r_lat, r_lon = index.from_box_name(tokens[:i]).centroid()
                print '"{}" resolves back to {},{}'.format(' '.join(tokens[:i]), r_lat, r_lon)

