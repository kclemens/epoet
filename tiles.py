import sqlite3

class GeoPoet(object):
    def __init__(self, dbname='words.sqlite3db', line_pattern=['--^-', '-^--', '^-^-'], rhyme='EY:fricative:AH:nasal', line_count=3):
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
