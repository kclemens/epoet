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
        distributions = [.5, .8, 1]

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

    def get_word_variants(self, word_text):
        return self.assemble_from_db('where text = ?', (word_text.lower(),))

    def get_random_word(self, stress, word_type=None, rhyme=None):
        if not word_type and not rhyme:
            words = self.assemble_from_db('where stress = ?', (stress,))
        elif not word_type:
            words = self.assemble_from_db('where stress = ? and rhyme = ?', (stress, rhyme))
        elif not rhyme:
            words = self.assemble_from_db('where stress = ? and type = ?', (stress, word_type))
        else:
            words = self.assemble_from_db('where stress = ? and rhyme = ? and type = ?', (stress, rhyme, word_type))

        return Word.choice(words)[0]

    def next_word(self, stress):
        stresses = [stress[:i] for i in range(1, len(stress) - 1)]
        logging.debug('fetching words for %s possible stress prefixes from requested stress %s', len(stresses), stress)
        words = self.connection.execute('''
            select text, rhyme, stress, complexity, sound
            from word
            where stress in (%s)
            ''' % ','.join('?' * len(stresses)), stresses)
        words = map(lambda params:Word(*params), words)
        logging.debug('fetched and parsed %s words', len(words))
        return Word.choice(words)

    def last_word(self, stress, rhyme_word=None):
        if rhyme_word:
            logging.debug('fetching word for stress %s rhyming with %s', stress, rhyme_word.text)
            words = self.connection.execute('''
                select text, rhyme, stress, complexity, sound
                from word
                where stress = ?
                and rhyme = ?
                and text <> ?''', (stress, rhyme_word.rhyme, rhyme_word.text))
        else:
            logging.debug('fetching word for stress %s and any rhyme', stress)
            words = self.connection.execute('''
                select text, rhyme, stress, complexity, sound
                from word
                where stress = ?''', (stress,))
        words = map(lambda params:Word(*params), words)
        logging.debug('fetched and parsed %s words', len(words))
        return Word.choice(words)

class PoemPattern(object):
    def __init__(self, index, text):
        self.line_stress_counts = collections.Counter()
        self.line_stress_lengths = collections.defaultdict(list)
        self.line_type_counts = collections.Counter()

        self.line_count = self.empty_count = self.comment_count = self.token_count = 0
        for line in text:
            self.process_line(line)

        logging.info('parsed %s lines (skipped %s empties and %s comments) and %s tokens',
                     self.line_count, self.empty_count, self.comment_count, self.token_count)
        logging.info('got %s line stresses:', sum(self.line_stress_counts.itervalues()))
        for stress, count in self.line_stress_counts.most_common(20):
            logging.info('%5d : %s', count, stress)
        logging.info('got %s line types:', sum(self.line_type_counts.itervalues()))
        for word_type, count in self.line_type_counts.most_common(20):
            logging.info('%5d : %s', count, word_type)

    @classmethod
    def all_combinations(cls, list_of_iterables):
        """
        recursive method for traversing lists of iterables

        iterables may not be empty

        yields every possible path through the list whith each path touching one element from each iterable
        """
        if len(list_of_iterables) == 1:
            for element in list_of_iterables[0]:
                yield [element]
        else:
            for element in list_of_iterables[0]:
                for suffix in cls.all_combinations(list_of_iterables[1:]):
                    yield [element] + suffix

    @classmethod
    def all_combinations_count(cls, list_of_iterables):
        count = 1
        for iterable in list_of_iterables:
            count *= len(iterable)
        return count

    def process_line(self, line):
        self.line_count += 1

        if line[0] == '#':
            self.comment_count += 1
            return

        line = line.strip()
        words = re.findall('[\w\']+', line)

        if not words:
            self.empty_count += 1
            return

        logging.info('on line %d processing %d tokens: %s', self.line_count, len(words), line)

        # count tokens for stats
        self.token_count += len(words)

        # replace each token with possible word variants
        # line is a list of lists; inner lists hold word variants (sound, stress, and type variants) for each token
        words = list(map(lambda token: list(index.get_word_variants(token)), words))

        # do not proceed if a word is not known
        for word_variant_list in words:
            if not word_variant_list:
                return

        # collect stresses
        stresses = map(lambda word_variant_list: map(lambda word: word.stress, word_variant_list), words)
        stresses = map(set, stresses)
        stresses = self.all_combinations(stresses)
        stresses = map(lambda combination: ''.join(combination), stresses)
        self.line_stress_counts.update(stresses)

        # collect word types
        types = map(lambda word_variant_list: map(lambda word: word.types, word_variant_list), words)
        types = map(lambda type_variants_lists: sum(type_variants_lists, list()), types)
        types = map(set, types)
        if self.all_combinations_count(list(types)) < 1000:
            types = self.all_combinations(types)
            types = map(lambda type_combination: '-'.join(type_combination), types)
            self.line_type_counts.update(types)
        else:
            logging.warning('too many word type combinations in line %s. skipping it as source for valid types.', line)

        logging.debug('processed %d line with %d tokens: %s', self.line_count, len(words), line)

class Poem(object):
    @classmethod
    def limmerick(cls, title, index):
        return cls(
            title,
            index,
            'A-^--^--^ '
            'A-^--^--^ '
            'B-^--^- '
            'B-^--^- '
            'A-^--^--^ '
        )

    def __init__(self, title, index, patterns='A-^--^--^--^ B-^--^--^ A-^--^--^--^ B-^--^--^'):
        self.title = title

        def lines(patterns, rhymes, poem):
            rhyme, stress = patterns[0][0], patterns[0][1:]
            stress_length = float(len(stress))
            line = list()

            while len(stress)/stress_length > .33:
                # fill at least two two thirds of the remaining stress with non-rhyme words
                next_word = index.next_word(stress)

                if not next_word:
                    # anbort if no next word
                    logging.warning('could not find next word!')
                    logging.warning('for pattern     %s', patterns[0])
                    logging.warning('reuqired stress %s', stress)
                    logging.warning('have so far     %s', map(lambda word:word.text, line))
                    logging.warning('have so far     %s', map(lambda word:word.stress, line))
                    return None
                else:
                    line.append(next_word)
                    stress = stress[len(next_word.stress):]

            next_word = index.last_word(stress, rhymes.get(rhyme))
            if not next_word:
                logging.debug('failed to generate line "%s"', line)
                logging.debug('got so far: %s', ' '.join(map(lambda x:x.text, line)))
                logging.debug('required rhyme: %s', rhymes.get(rhyme))
                logging.debug('remaining stress: %s', stress)
                return None
            else:
                line.append(next_word)
                rhymes[rhyme] = next_word
                logging.debug('got next line: %s', map(lambda word:word.text, line))

                if len(patterns) == 1:
                    poem.append(line)
                    return poem

                next_lines = lines(patterns[1:], rhymes, poem)

                if not next_lines:
                    return lines(patterns, rhymes, poem)

                else:
                    return [line] + next_lines

        self.lines = lines(patterns.split(), dict(), list())

    def __repr__(self):
        result = '  {} - a poem by {}\n---\n'.format(self.title, socket.gethostname())
        for line in self.lines:
            for word in line:
                result += word.text + ' '
            result += '\n'
        result += '---\n  {}'.format(time.strftime('%B %Y'))
        return result

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)7s - %(message)s')

    # facade = WictionaryFacade()
    index = PoetryIndex()

    # index.load_words(Word.from_file(Phones.from_file(), facade))
    # print facade

    PoemPattern(index, open('poems.txt'))

    # import sys
    # if len(sys.argv) > 1:
    #     base_path = sys.argv[1]
    #     index = InMemoryPoetryIndex(Word.from_file(Phones.from_file(base_path+'/cmudict.phones'), base_path+'/cmudict.dict'))
    # else:
    #     # default location: cmudict next to epoet
    #     index = InMemoryPoetryIndex(Word.from_file(Phones.from_file()))

    # index = PoetryIndex()
    # index.re_load_words(Word.from_file(Phones.from_file()))

    # print Poem('the void', index)
    # print Poem.limmerick('limeric', index)


