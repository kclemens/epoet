import sqlite3
import math

class Box(object):
    def __init__(self, min_x=-180, min_y=-90, max_x=180, max_y=90):
        self.max_y = max_y
        self.max_x = max_x
        self.min_y = min_y
        self.min_x = min_x

    def get_sub_box(self, index, count):
        # get number of possible sub-boxes
        q = math.floor(math.sqrt(count))
        if q*(q + 1) < count:
            rows, cols = q, q + 1
        else:
            rows, cols = q, q

        assert index < rows * cols

        row = 0
        while index < row * cols:
            row += 1

        column = index - row * cols

        row_width = self.max_x - self.min_x / rows
        col_width

    def get_super_box(self, index, count):
        pass


class GeoPoet(object):
    def __init__(self, dbname='words.sqlite3db', line_pattern=list(['--^-', '-^--', '^-^-']), rhyme='EY:fricative:AH:nasal', line_count=3):
        self.connection = sqlite3.connect(dbname)
        self.line_pattern = line_pattern
        self.rhyme = rhyme
        self.line_count = line_count

    def calculate_resolution(self):
        count = 1
        for word_stress in self.line_pattern[:-1]:
            count *= self.connection.execute('select count (distinct text) from word where stress = ?', (word_stress,)).fetchone()[0]

        count *= self.connection.execute('select count (distinct text) from word where stress = ? and rhyme = ?', (self.line_pattern[-1], self.rhyme)).fetchone()[0]

        return (40000000.0*20000000.0)/pow(count, self.line_count)

if __name__ == '__main__':
    gp = GeoPoet(line_count=2)

    print gp.calculate_resolution()
