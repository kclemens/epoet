import logging
import collections
import random
import socket
import time
import sqlite3
import urllib2
import json
import re

class Phones(object):
    @classmethod
    def from_file(cls, filename='../cmudict/cmudict.phones'):
        logging.info('loading phones from "%s"', filename)

        def lines():
            for line in open(filename):
                line = line.strip()
                logging.debug('adding phone from line "%s"', line)
                yield line

        return cls(lines())

    def __init__(self, phones_lines):
        self.phones = map(str.split,phones_lines)
        self.phones = dict(self.phones)

        logging.info('got %s phones.', len(self.phones))

    def __repr__(self):
        return 'phones:\n' + '\n'.join(map(lambda item: '{:>3s}:{:s}'.format(*item), self.phones.items()))

    def validate(self, phones):
        for phone in phones:
            phone_no_stress = phone[:2] # cut off stress indicator
            assert phone_no_stress in self.phones, 'unexpected phone "{}" in "{}"'.format(phone, ':'.join(phones))

    def get_type(self, phone):
        phone_no_stress = phone[:2] # cut off stress indicator
        assert phone_no_stress in self.phones, 'unexpected phone "{}"'.format(phone)
        return self.phones[phone_no_stress]

    def is_complex_pair(self, phone_pair):
        phone_a, phone_b = phone_pair
        both_vowel = (self.phones[phone_a] == 'vowel') and (self.phones[phone_b] == 'vowel') and (phone_a != phone_b)
        both_not_vowel = (self.phones[phone_a] != 'vowel') and (self.phones[phone_b] != 'vowel')
        # consecutive = self.phones[phone_a] == self.phones[phone_b]
        return both_vowel or both_not_vowel

class WictionaryFacade(object):
    base_url = 'https://en.wiktionary.org/w/api.php?action=parse&format=json&prop=wikitext&page='
    known_types=['noun', 'pronoun', 'verb', 'interjection', 'adjective', 'adverb', 'preposition', 'postposition', 'particle', 'conjuction', 'determiner']

    def __init__(self):
        self.counts_known_types = collections.Counter()
        self.counts_all_types = collections.Counter()
        self.calls = 0

    def get_word_types(self, word, tries=5):
        self.calls += 1

        while tries:
            try:
                url = self.base_url + urllib2.quote(word)
                logging.debug('fetching from %s', url)
                data = urllib2.urlopen(url)
                data = json.load(data)

                if 'parse' in data:
                    tags = re.findall('\n=+(.*?)=+\n', data['parse']['wikitext']['*'].encode('utf8'))

                    tags = set(map(str.lower, tags))
                    self.counts_all_types.update(collections.Counter(tags))

                    tags = set(filter(lambda tag: tag in self.known_types, tags))
                    self.counts_known_types.update(collections.Counter(tags))

                    return sorted(tags)
                else:
                    break
            except Exception:
                tries -= 1
                if tries:
                    logging.warn('could not get word types for "%s". retrying.', word)
                else:
                    logging.warn('could not get word types for "%s". assigning "other".', word)

        return ['other']

    def __repr__(self):
        return 'WictionaryFacade was invoked {} times\n' .format(self.calls)+ \
               '{:s}\n'.format(self.counts_known_types.most_common(100)) +\
               '{:s}\n'.format(self.counts_all_types.most_common(10))

class Word(object):
    @classmethod
    def from_file(cls, phones, wictionary, filename='../cmudict/cmudict.dict', limit=0):
        logging.info('loading words from "%s"', filename)
        count = 0
        for count, line in enumerate(open(filename)):
            line = line.strip()
            word = cls.from_line(phones, wictionary, line)
            yield word

            if limit and count == limit:
                break

        logging.info('loaded %s words', count)

    @classmethod
    def from_line(cls, phones, wictionary, line):
        '''d'artagnan D AH0 R T AE1 NG Y AH0 N # foreign french'''

        logging.debug('parsing word from line "%s"', line)

        if '#' in line:
            line = line[:line.find('#')]

        tokens = line.split()
        if tokens[0][-1] == ')':
            text = tokens[0][:-3]
        else:
            text = tokens[0]
        logging.debug('got text %s', text)

        phones.validate(tokens[1:])

        last_stress_index = 0
        for i, token in enumerate(tokens[1:]):
            if len(token) == 3 and int(token[2]) > 0:
                last_stress_index = i
        rhyme = tokens[1:][last_stress_index:]
        rhyme = map(lambda token: token[:2] if len(token) == 3 else phones.get_type(token), rhyme)
        rhyme = ':'.join(rhyme)
        logging.debug('got rhyme %s', rhyme)

        stress = filter(lambda token: len(token) == 3, tokens[1:])
        stress = map(lambda token: '^' if int(token[2]) > 0 else '-', stress)
        stress = ''.join(stress)
        logging.debug('got stress %s', stress)

        complexity = list(map(lambda token: token[:2], tokens[1:]))
        complexity = list(zip(complexity, complexity[1:]))
        complexity = list(filter(lambda pair: phones.is_complex_pair(pair),complexity))
        complexity = float(len(complexity))/len(text)

        sound = ':'.join(tokens[1:])
        logging.debug('got sound %s', sound)

        types = wictionary.get_word_types(text)
        logging.debug('got types %s', types)

        return cls(text, sound, stress, rhyme, complexity, types)

    def __init__(self, text, sound, stress, rhyme, complexity, types):
        self.text = text
        self.rhyme = rhyme
        self.stress = stress
        self.complexity = complexity
        self.sound = sound
        self.types = types

    def __repr__(self):
        return self.text
        # return '|{:^50s} | {:^30s} | {:^70s} | {:^4.2f} | {:^10s} | {:^50s}|'.format(
        #     self.text, ','.join(self.types), self.sound, self.complexity, self.stress, self.rhyme)

    @staticmethod
    def choice(words):
        words = list(words)

        logging.debug('chosing one out of %s words', len(words))

        if not words:
            return None

        # pick a random matching word
        # return random.choice(words)

        # pick most simple words with higher probability
        max_complexity = max(map(lambda word: word.complexity, words))
        min_complexity = min(map(lambda word: word.complexity, words))
        complexity_quarter_width = (max_complexity - min_complexity) / 4.0
        first_quarter = min_complexity + complexity_quarter_width
        second_quarter = first_quarter + complexity_quarter_width

        # words with complexity in the lowest quarter
        easy_words = list(filter(lambda word: word.complexity <= first_quarter, words))

        # words with complexity in the second quarter
        medium_words = list(filter(lambda word: first_quarter < word.complexity <= second_quarter, words))

        # words with complexity in the second half
        complex_words = list(filter(lambda word: word.complexity > second_quarter, words))

        classes = [easy_words, medium_words, complex_words]
        distributions = [.8, 1, 1]

        choice = random.random()

        for i, threshold in enumerate(distributions):
            if choice <= threshold and classes[i]:
                return random.choice(classes[i])

        logging.warning('could not return word')
        logging.warning('got %s words in total', len(words))
        logging.warning('got min complexity %s', min_complexity)
        logging.warning('got max complexity %s', max_complexity)
        logging.warning('got first complexity quarter threshold %s', first_quarter)
        logging.warning('got second complexity quarter threshold %s', second_quarter)
        logging.warning('got %s words in easy class', len(complex_words))
        logging.warning('got %s words in medium class', len(medium_words))
        logging.warning('got %s words in complex class', len(complex_words))
        logging.warning('got threshold %s and choice %s', distributions, choice)
        raise Exception('something went wrong when chosing a word!')

class PoetryIndex(object):
    def __init__(self, dbname='words.sqlite3db'):
        self.connection = sqlite3.connect(dbname)
        self.connection.execute('''
            create table if not exists word (
                text text not null,
                rhyme text not null,
                stress text not null,
                sound text not null,
                complexity float not null,
                type text not null
            )''')
        self.connection.execute('create index if not exists word_text on word(text)')
        self.connection.execute('create index if not exists word_rhyme on word(rhyme)')
        self.connection.execute('create index if not exists word_stress on word(stress)')
        self.connection.execute('create index if not exists word_complexity on word(complexity)')
        self.connection.execute('create index if not exists word_type on word(type)')

        wordcount = self.connection.execute('select count (*) from word').fetchone()[0]

        logging.info('connected to index %s with %s word index entries', dbname, wordcount)

    def load_words(self, words):
        self.connection.execute('delete from word')

        def flat_words():
            for count, word in enumerate(words, 1):
                if count % 10 == 1:
                    logging.info('adding word %d: "%s"', count, word)
                    self.connection.commit()
                else:
                    logging.debug('adding word %d: "%s"', count, word)
                for word_type in word.types:
                    yield word.text, word.rhyme, word.stress, word.sound, word.complexity, word_type

        self.connection.executemany('''
            insert into word (
                text,
                rhyme,
                stress,
                sound,
                complexity,
                type
        ) values (?, ?, ?, ?, ?, ?)''', flat_words())
        self.connection.commit()

        wordcount = self.connection.execute('select count (*) from word').fetchone()[0]
        logging.info('re indexed %s words.', wordcount)

    def assemble_from_db(self, where_condition, params):
        rows = self.connection.execute(
            'select text, sound, stress, rhyme, complexity, type ' +
            'from word ' +
            where_condition + ' ' +
            'order by text, sound, stress', params)
        rows = rows.fetchall()

        if rows:
            word = None
            for row in rows:
                if not word:
                    word = Word(row[0], row[1], row[2], row[3], row[4], [row[5]])
                elif row[0] != word.text or row[1] != word.sound:
                    yield word
                    word = Word(row[0], row[1], row[2], row[3], row[4], [row[5]])
                else:
                    word.types.append(row[5])
            yield word

    def get_random_word(self, stress, word_type=None, rhyme=None):
        if not word_type and not rhyme:
            words = self.assemble_from_db('where stress = ?', (stress,))
        elif not word_type:
            words = self.assemble_from_db('where stress = ? and rhyme = ?', (stress, rhyme))
        elif not rhyme:
            words = self.assemble_from_db('where stress = ? and type = ?', (stress, word_type))
        else:
            words = self.assemble_from_db('where stress = ? and rhyme = ? and type = ?', (stress, rhyme, word_type))

        return Word.choice(words)

class Poem(object):
    @classmethod
    def limmerick(cls, title, index):
        return cls(
            title,
            index,
            'A -^--^--^ 3:6\n' +
            'A -^--^--^ 3:6\n' +
            'B -^--^- 2:4\n' +
            'B -^--^- 2:4\n' +
            'A -^--^--^ 3:6'
        )

    def __init__(self, title, index, pattern='A -^--^--^--^ 2:8\nB -^--^--^ 1:3\nA -^--^--^--^ 2:8\nB -^--^--^ 1:3', tries=10):
        self.title = title
        self.lines = list()

        def splits(to_split, split_count):
            if split_count == 1:
                yield [to_split]
            else:
                for i in range(1, len(to_split)):
                    for suffix in splits(to_split[i:], split_count - 1):
                        yield [to_split[:i]] + list(suffix)

        def splits_variant(to_split, min_count, max_count):
            for count in range(min_count, max_count + 1):
                for split in splits(to_split, count):
                    yield split

        rhymes = dict()
        for line in pattern.split('\n'):
            line_rhyme, line_stress, line_words = line.split(' ')
            min_words, max_words = map(int, line_words.split(':'))

            while True:

                tries -= 1
                if not tries:
                    logging.warn('could not generate line %s', line)
                    logging.warn('have words     : %s', line)
                    logging.warn('required rhyme : %s', rhymes.get(line_rhyme))
                    logging.warn('required stress: %s', word_stress)
                    logging.warn('last word      : %s', word_index == len(word_stresses))

                line = list()
                word_stresses = random.choice(list(splits_variant(line_stress, min_words, max_words)))
                for word_index, word_stress in enumerate(word_stresses, 1):
                    if word_index < len(word_stresses):
                        word = index.get_random_word(word_stress)
                        if not word:
                            continue
                        line.append(word.text)
                    else:
                        word = index.get_random_word(word_stress, rhyme=rhymes.get(line_rhyme))
                        if not word:
                            continue
                        rhymes[line_rhyme] = word.rhyme
                        line.append(word.text)
                break

            self.lines.append(' '.join(line))

    def __repr__(self):
        result = '  {} - a poem by {}\n---\n'.format(self.title, socket.gethostname())
        result += '\n'.join(self.lines)
        return result

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)7s - %(message)s')

    # facade = WictionaryFacade()
    index = PoetryIndex()
    # index.load_words(Word.from_file(Phones.from_file(), facade))
    # print facade



    # import sys
    # if len(sys.argv) > 1:
    #     base_path = sys.argv[1]
    #     index = InMemoryPoetryIndex(Word.from_file(Phones.from_file(base_path+'/cmudict.phones'), base_path+'/cmudict.dict'))
    # else:
    #     # default location: cmudict next to epoet
    #     index = InMemoryPoetryIndex(Word.from_file(Phones.from_file()))

    # index = PoetryIndex()
    # index.re_load_words(Word.from_file(Phones.from_file()))

    print Poem('the void', index)
    print Poem.limmerick('limeric', index)


