import sqlite3
import math

class Box(object):
    def __init__(self, min_x=-180.0, min_y=-90.0, max_x=180.0, max_y=90.0):
        self.max_y = max_y
        self.max_x = max_x
        self.min_y = min_y
        self.min_x = min_x

    def __repr__(self):
        return 'Box {},{}  {},{}'.format(self.min_x, self.min_y, self.max_x, self.max_y)
        # return 'http://maps.google.com/maps/api/staticmap?size=500x300&sensor=false&path=color:0x00000000|weight:5|fillcolor:0xFFFF0033|{},{}|{},{}|{},{}|{},{}'.format(
        #     self.min_x, self.min_y,
        #     self.max_x, self.min_y,
        #     self.max_x, self.max_y,
        #     self.min_x, self.max_y,
        # )

    def sub_box_index(self, x, y, box_count):
        q = math.sqrt(box_count)

        assert q == math.floor(q)

        x = math.floor((x - self.min_x) / (self.max_x - self.min_x) * q)
        y = math.floor((y - self.min_y) / (self.max_y - self.min_y) * q)

        return q*y + x

    def sub_box(self, box_index, box_count):
        q = math.sqrt(box_count)

        assert q == math.floor(q)

        x = math.floor(box_index / q)
        y = box_index - x * q

        assert x < q and y < q

        x_width = (self.max_x - self.min_x) / q
        y_width = (self.max_y - self.min_y) / q

        return Box(
            x_width * x + self.min_x,
            y_width * y + self.min_y,
            x_width * (x + 1) + self.min_x,
            y_width * (y + 1) + self.min_y
        )

    def super_box(self, box_index, box_count):
        q = math.sqrt(box_count)

        assert q == math.floor(q)

        x = math.floor(box_index / q)
        y = box_index - x * q

        assert x < q and y < q

        x_width = (self.max_x - self.min_x)
        y_width = (self.max_y - self.min_y)

        return Box(
            self.min_x - x_width * x,
            self.min_y - y_width * y,
            self.min_x + x_width * (q - x),
            self.min_y + y_width * (q - y)
        )

class BoxIndex(object):
    def __init__(self, options, repeats, outer_box=Box()):
        self.options = options
        self.repeats = repeats
        self.outer_box = outer_box

    def to_box_name(self, lat, lon):
        box = self.outer_box
        name = list()

        for _ in xrange(self.repeats):
            for options in self.options:
                count = len(options)

                index = box.sub_box_index(lat, lon, count)

                name.append(self.options[index])
                box = box.sub_box(index, count)

        return name

    def from_box_name(self, name):
        box = self.outer_box

        for i, token in enumerate(name):
            index = self.options[i % len(self.options)].index(token)
            count = len(self.options[i % len(self.options)])

            box = box.super_box(index, count)

        return box

class GeoPoet(object):
    def __init__(self, dbname='words.sqlite3db', line_pattern=list(['^-^', '-^-^-']), rhyme='EY:fricative:AH:nasal', line_count=3):
        self.connection = sqlite3.connect(dbname)
        self.line_pattern = line_pattern
        self.rhyme = rhyme
        self.line_count = line_count

    def generate_line_options(self):
        line_options = list()
        for word_stress in self.line_pattern[:-1]:
            words = self.connection.execute('select distinct from word where stress = ?', (word_stress,))
            words = list(map(lambda row: row[0], words))
            word_count = math.pow(math.floor(math.sqrt(len(words))), 2)
            line_options.append(words[:word_count])

        words = self.connection.execute('select distinct text from word where stress = ? and rhyme = ?', (self.line_pattern[-1], self.rhyme))
        words = list(map(lambda row: row[0], words))
        word_count = math.pow(math.floor(math.sqrt(len(words) - 1)), 2) + 1
        line_options.append(words[:word_count])

        return line_options

    def calculate_resolution(self):
        total_count = 1
        for word_stress in self.line_pattern[:-1]:
            word_count = self.connection.execute('select count (distinct text) from word where stress = ?', (word_stress,)).fetchone()[0]
            word_count = math.pow(math.floor(math.sqrt(word_count)), 2)
            total_count *= word_count

        word_count = self.connection.execute('select count (distinct text) from word where stress = ? and rhyme = ?', (self.line_pattern[-1], self.rhyme)).fetchone()[0]
        word_count = math.pow(math.floor(math.sqrt(word_count - 1)), 2)
        total_count *= word_count

        return (40000000.0*20000000.0)/pow(total_count, self.line_count)

if __name__ == '__main__':
    box = Box(0, 0, 4, 4)
    print box.sub_box_index(1, 1, 4)
    print box.sub_box_index(3, 1, 4)
    print box.sub_box_index(3, 3, 4)
    print box.sub_box_index(1, 3, 4)

    # print GeoPoet(line_pattern=['^-^-^-', '-^-^-'], rhyme='EY:fricative:AH:nasal', line_count=4).calculate_resolution()

    # print GeoPoet(line_pattern=['^--^-', '^--^-'], rhyme='EY:fricative:AH:nasal', line_count=3).calculate_resolution()
