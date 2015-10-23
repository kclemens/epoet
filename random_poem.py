import logging
import collections
import random
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

        easy_words = list(filter(lambda word: word.complexity < first_quarter, words))
        easy_and_medium_words = list(filter(lambda word: word.complexity < second_quarter, words))
        all_words = words

        classes = [easy_words, easy_and_medium_words, words]
        distributions = [.7, .8, 1.0]

        choice = random.random()

        for i, threshold in enumerate(distributions):
            if choice < threshold and classes[i]:
                return random.choice(classes[i])

        logging.warning('could not return word')
        logging.warning('got %s words in total', len(words))
        logging.warning('got min complexity %s', min_complexity)
        logging.warning('got max complexity %s', max_complexity)
        logging.warning('got first complexity quarter threshold %s', first_quarter)
        logging.warning('got second complexity quarter threshold %s', second_quarter)
        logging.warning('got %s words in easy class', len(easy_words))
        logging.warning('got %s words in medium class', len(easy_and_medium_words))
        logging.warning('got %s words in all class', len(words))
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

    def enhance_stresses(self):
        #prepare shadow table
        self.connection.execute('''
            create table if not exists e_word (
                text text not null,
                rhyme text not null,
                stress text not null,
                sound text not null,
                complexity float not null,
                type text not null
            )''')
        self.connection.execute('create index if not exists e_word_text on e_word(text)')
        self.connection.execute('create index if not exists e_word_rhyme on e_word(rhyme)')
        self.connection.execute('create index if not exists e_word_stress on e_word(stress)')
        self.connection.execute('create index if not exists e_word_complexity on e_word(complexity)')
        self.connection.execute('create index if not exists e_word_type on e_word(type)')

        words = self.connection.execute('select text, sound, stress, rhyme, complexity, type from word order by text')

        current_text = None
        sounds = list()
        stresses = list()
        rhymes = list()
        complexities = list()
        word_types = list()
        count = 0

        def enhance(count):
            logging.debug('enhancing %s', current_text)
            stress_lenghts = set(map(len, stresses))

            # add all-stress variants for single-stress words
            if 1 in stress_lenghts and '^' not in stresses:
                for i in range(count):
                    sounds.append(sounds[i])
                    stresses.append('^')
                    rhymes.append(rhymes[i])
                    complexities.append(complexities[i])
                    word_types.append(word_types[i])
                    count += 1

            # generate no-stress variants
            no_stresses = map(lambda stress_length: '-'*stress_length, stress_lenghts)
            for no_stress in no_stresses:
                if no_stress not in stresses:
                    for i in range(count):
                        sounds.append(sounds[i])
                        stresses.append(no_stress)
                        rhymes.append(rhymes[i])
                        complexities.append(complexities[i])
                        word_types.append(word_types[i])
                        count += 1

            # write word back to db
            def tupelize():
                for i in range(count):
                    logging.debug('%s', (current_text, sounds[i], stresses[i], rhymes[i], complexities[i], word_types[i]))
                    yield (current_text, sounds[i], stresses[i], rhymes[i], .1*count + complexities[i], word_types[i])

            self.connection.executemany('''
               insert into e_word (text, sound, stress, rhyme, complexity, type) values (?, ?, ?, ?, ?, ?)
            ''', tupelize())

        for text, sound, stress, rhyme, complexity, word_type in words:
            if not current_text:
                current_text = text

            if current_text != text:
                enhance(count)

                current_text = text
                sounds = list()
                stresses = list()
                rhymes = list()
                complexities = list()
                word_types = list()
                count = 0

            sounds.append(sound)
            stresses.append(stress)
            rhymes.append(rhyme)
            complexities.append(complexity)
            word_types.append(word_type)
            count += 1

        enhance(count)
        self.connection.commit()
        logging.info('have %s enhanced index entries', self.connection.execute('select count (*) from e_word').fetchone()[0])
        logging.info('switching to enchanced table...')
        self.connection.execute('drop table word')
        self.connection.execute('alter table e_word rename to word')
        logging.info('done enhancing')

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

    def get_words(self, stress, word_type=None, rhyme=None):
        if not word_type and not rhyme:
            words = self.assemble_from_db('where stress = ?', (stress,))
        elif not word_type:
            words = self.assemble_from_db('where stress = ? and rhyme = ?', (stress, rhyme))
        elif not rhyme:
            words = self.assemble_from_db('where stress = ? and type = ?', (stress, word_type))
        else:
            words = self.assemble_from_db('where stress = ? and rhyme = ? and type = ?', (stress, rhyme, word_type))

        return words

    def get_word_count(self, stress, rhyme=None):
        if rhyme:
            query_n_param = ('select count (distinct text) from word where stress = ? and rhyme = ?', (stress, rhyme))
        else:
            query_n_param = ('select count (distinct text) from word where stress = ?', (stress,))

        logging.debug('querying : %s', query_n_param)
        row = self.connection.execute(*query_n_param).fetchone()
        return row[0]

    def get_word_variants(self, text):
        return self.assemble_from_db('where text = ?', (text.lower(),))

    def known_rhyme_types(self):
        for row in self.connection.execute('select distinct rhyme from word'):
            yield row[0]

    def __repr__(self):
        return 'poetry index with {} indexed entries ({} distinct words)\n'.format(
            *self.connection.execute('select count (*), count (distinct text) from word').fetchone())

class PoemPatternLearner(object):
    def __init__(self, index, text):
        self.index = index
        self.line_type_counts = {
            0: collections.Counter(),
            1: collections.Counter(),
            2: collections.Counter(),
            3: collections.Counter(),
            4: collections.Counter(),
            5: collections.Counter(),
            6: collections.Counter(),
            7: collections.Counter(),
            8: collections.Counter(),
            9: collections.Counter(),
        }

        self.line_count = self.empty_count = self.comment_count = self.token_count = 0
        for line in text:
            self.process_line(line)

        logging.info('parsed %s lines (skipped %s empties and %s comments) and %s tokens',
                     self.line_count, self.empty_count, self.comment_count, self.token_count)

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
        words = list(map(lambda token: list(self.index.get_word_variants(token)), words))

        # do not proceed if a word is not known
        for word_variant_list in words:
            if not word_variant_list:
                return

        # collect word types
        types = map(lambda word_variant_list: map(lambda word: word.types, word_variant_list), words)
        types = map(lambda type_variants_lists: sum(type_variants_lists, list()), types)
        types = list(map(set, types))
        if self.all_combinations_count(types) < 1000000:
            word_count = len(types) if len(types) < 10 else 0
            types = self.all_combinations(types)
            types = map(lambda type_combination: '-'.join(type_combination), types)
            self.line_type_counts[word_count].update(types)
        else:
            logging.warning('too many word type combinations in line %s. skipping it as source for valid types.', line)

        logging.debug('processed %d line with %d tokens: %s', self.line_count, len(words), line)

    def __repr__(self):
        result = '    line_patterns = {\n'
        for token_count in range(1, 10):
            result += '        {:d}: [  # {:d} cases\n'.format(token_count, sum(self.line_type_counts[token_count].values()))
            for token_type_list, count in self.line_type_counts[token_count].most_common(20):
                result += '            [\'{:s}\'],  # {:d} occurrences \n'.format('\', \''.join(token_type_list.split('-')), count)
            result += '        ],\n'
        result += '    }\n'

        return result

class Poem(object):

    # collected using PoemPatternLearner
    line_patterns = {
        1: [  # 2 cases
            ['verb'],  # 1 occurrences
            ['noun'],  # 1 occurrences
        ],
        2: [  # 54 cases
            ['adjective', 'noun'],  # 8 occurrences
            ['noun', 'noun'],  # 7 occurrences
            ['verb', 'noun'],  # 7 occurrences
            ['noun', 'adjective'],  # 3 occurrences
            ['adjective', 'adjective'],  # 3 occurrences
            ['pronoun', 'noun'],  # 2 occurrences
            ['adverb', 'noun'],  # 2 occurrences
            ['verb', 'adjective'],  # 2 occurrences
            ['noun', 'adverb'],  # 1 occurrences
            ['verb', 'adverb'],  # 1 occurrences
            ['pronoun', 'adjective'],  # 1 occurrences
            ['determiner', 'noun'],  # 1 occurrences
            ['pronoun', 'adverb'],  # 1 occurrences
            ['determiner', 'adjective'],  # 1 occurrences
            ['preposition', 'noun'],  # 1 occurrences
            ['adjective', 'verb'],  # 1 occurrences
            ['adverb', 'verb'],  # 1 occurrences
            ['preposition', 'verb'],  # 1 occurrences
            ['adverb', 'adverb'],  # 1 occurrences
            ['postposition', 'adverb'],  # 1 occurrences
        ],
        3: [  # 1286 cases
            ['noun', 'noun', 'noun'],  # 26 occurrences
            ['verb', 'noun', 'noun'],  # 24 occurrences
            ['verb', 'adverb', 'noun'],  # 23 occurrences
            ['verb', 'adjective', 'noun'],  # 21 occurrences
            ['noun', 'adjective', 'noun'],  # 21 occurrences
            ['noun', 'adverb', 'noun'],  # 19 occurrences
            ['noun', 'noun', 'verb'],  # 19 occurrences
            ['verb', 'noun', 'verb'],  # 18 occurrences
            ['noun', 'adverb', 'verb'],  # 17 occurrences
            ['noun', 'verb', 'noun'],  # 17 occurrences
            ['verb', 'adverb', 'verb'],  # 17 occurrences
            ['adverb', 'noun', 'noun'],  # 17 occurrences
            ['noun', 'adjective', 'verb'],  # 16 occurrences
            ['verb', 'determiner', 'noun'],  # 16 occurrences
            ['adverb', 'adjective', 'noun'],  # 16 occurrences
            ['noun', 'verb', 'verb'],  # 15 occurrences
            ['verb', 'adjective', 'verb'],  # 15 occurrences
            ['verb', 'verb', 'noun'],  # 15 occurrences
            ['adverb', 'adverb', 'noun'],  # 15 occurrences
            ['noun', 'determiner', 'noun'],  # 14 occurrences
        ],
        4: [  # 10228 cases
            ['noun', 'noun', 'noun', 'noun'],  # 37 occurrences
            ['noun', 'noun', 'noun', 'verb'],  # 34 occurrences
            ['noun', 'verb', 'noun', 'verb'],  # 34 occurrences
            ['noun', 'verb', 'noun', 'noun'],  # 33 occurrences
            ['noun', 'noun', 'verb', 'noun'],  # 30 occurrences
            ['adverb', 'noun', 'noun', 'verb'],  # 29 occurrences
            ['noun', 'verb', 'adverb', 'noun'],  # 29 occurrences
            ['adverb', 'noun', 'noun', 'noun'],  # 29 occurrences
            ['noun', 'noun', 'adverb', 'noun'],  # 29 occurrences
            ['adverb', 'noun', 'verb', 'noun'],  # 27 occurrences
            ['noun', 'verb', 'verb', 'noun'],  # 27 occurrences
            ['adverb', 'verb', 'noun', 'verb'],  # 27 occurrences
            ['noun', 'verb', 'adverb', 'verb'],  # 27 occurrences
            ['verb', 'noun', 'noun', 'noun'],  # 26 occurrences
            ['noun', 'noun', 'verb', 'verb'],  # 26 occurrences
            ['noun', 'verb', 'verb', 'verb'],  # 26 occurrences
            ['noun', 'adverb', 'noun', 'noun'],  # 26 occurrences
            ['noun', 'noun', 'adverb', 'verb'],  # 25 occurrences
            ['adverb', 'verb', 'noun', 'noun'],  # 25 occurrences
            ['verb', 'noun', 'verb', 'noun'],  # 24 occurrences
        ],
        5: [  # 38133 cases
            ['adverb', 'noun', 'noun', 'noun', 'noun'],  # 32 occurrences
            ['verb', 'noun', 'noun', 'noun', 'noun'],  # 31 occurrences
            ['adverb', 'noun', 'noun', 'noun', 'verb'],  # 28 occurrences
            ['noun', 'noun', 'verb', 'noun', 'noun'],  # 28 occurrences
            ['noun', 'noun', 'noun', 'noun', 'noun'],  # 27 occurrences
            ['adverb', 'noun', 'verb', 'noun', 'verb'],  # 27 occurrences
            ['adverb', 'noun', 'verb', 'noun', 'noun'],  # 27 occurrences
            ['adverb', 'noun', 'noun', 'verb', 'verb'],  # 25 occurrences
            ['noun', 'noun', 'verb', 'noun', 'verb'],  # 24 occurrences
            ['adverb', 'determiner', 'noun', 'noun', 'noun'],  # 24 occurrences
            ['adverb', 'adjective', 'noun', 'noun', 'noun'],  # 24 occurrences
            ['noun', 'verb', 'verb', 'noun', 'noun'],  # 23 occurrences
            ['verb', 'noun', 'verb', 'noun', 'noun'],  # 23 occurrences
            ['verb', 'noun', 'noun', 'verb', 'noun'],  # 23 occurrences
            ['noun', 'verb', 'noun', 'noun', 'noun'],  # 23 occurrences
            ['adverb', 'noun', 'noun', 'verb', 'noun'],  # 23 occurrences
            ['noun', 'noun', 'noun', 'noun', 'verb'],  # 23 occurrences
            ['verb', 'adjective', 'noun', 'noun', 'noun'],  # 22 occurrences
            ['adverb', 'noun', 'verb', 'verb', 'verb'],  # 22 occurrences
            ['verb', 'noun', 'verb', 'verb', 'noun'],  # 22 occurrences
        ],
        6: [  # 280978 cases
            ['noun', 'noun', 'noun', 'verb', 'noun', 'noun'],  # 53 occurrences
            ['adverb', 'noun', 'noun', 'verb', 'noun', 'noun'],  # 50 occurrences
            ['noun', 'noun', 'noun', 'verb', 'adverb', 'noun'],  # 49 occurrences
            ['noun', 'noun', 'noun', 'noun', 'noun', 'noun'],  # 49 occurrences
            ['noun', 'noun', 'noun', 'verb', 'noun', 'verb'],  # 47 occurrences
            ['adverb', 'noun', 'noun', 'noun', 'noun', 'noun'],  # 46 occurrences
            ['adverb', 'noun', 'noun', 'verb', 'adverb', 'noun'],  # 46 occurrences
            ['noun', 'noun', 'noun', 'noun', 'noun', 'verb'],  # 45 occurrences
            ['adverb', 'noun', 'noun', 'verb', 'noun', 'verb'],  # 45 occurrences
            ['noun', 'noun', 'noun', 'verb', 'adjective', 'noun'],  # 44 occurrences
            ['verb', 'noun', 'noun', 'verb', 'noun', 'noun'],  # 44 occurrences
            ['noun', 'noun', 'verb', 'verb', 'noun', 'noun'],  # 44 occurrences
            ['verb', 'noun', 'noun', 'noun', 'noun', 'noun'],  # 43 occurrences
            ['noun', 'noun', 'noun', 'verb', 'adverb', 'verb'],  # 43 occurrences
            ['noun', 'noun', 'noun', 'noun', 'adverb', 'noun'],  # 43 occurrences
            ['noun', 'adverb', 'noun', 'verb', 'noun', 'noun'],  # 42 occurrences
            ['noun', 'noun', 'noun', 'adverb', 'noun', 'noun'],  # 42 occurrences
            ['adverb', 'adverb', 'noun', 'verb', 'noun', 'noun'],  # 41 occurrences
            ['verb', 'noun', 'noun', 'noun', 'noun', 'verb'],  # 41 occurrences
            ['adverb', 'noun', 'noun', 'verb', 'adverb', 'verb'],  # 41 occurrences
        ],
        7: [  # 671728 cases
            ['noun', 'noun', 'noun', 'noun', 'verb', 'noun', 'noun'],  # 38 occurrences
            ['noun', 'noun', 'noun', 'noun', 'verb', 'noun', 'verb'],  # 37 occurrences
            ['adverb', 'noun', 'noun', 'noun', 'verb', 'noun', 'noun'],  # 35 occurrences
            ['noun', 'noun', 'noun', 'noun', 'noun', 'noun', 'noun'],  # 35 occurrences
            ['noun', 'noun', 'noun', 'noun', 'noun', 'noun', 'verb'],  # 34 occurrences
            ['adverb', 'noun', 'noun', 'noun', 'verb', 'noun', 'verb'],  # 34 occurrences
            ['noun', 'noun', 'noun', 'verb', 'noun', 'noun', 'noun'],  # 33 occurrences
            ['noun', 'noun', 'noun', 'verb', 'verb', 'noun', 'noun'],  # 32 occurrences
            ['adverb', 'noun', 'noun', 'noun', 'noun', 'noun', 'noun'],  # 32 occurrences
            ['noun', 'noun', 'noun', 'noun', 'verb', 'adverb', 'verb'],  # 31 occurrences
            ['adverb', 'noun', 'noun', 'noun', 'noun', 'noun', 'verb'],  # 31 occurrences
            ['noun', 'noun', 'noun', 'noun', 'adverb', 'noun', 'noun'],  # 30 occurrences
            ['adverb', 'noun', 'noun', 'verb', 'noun', 'noun', 'noun'],  # 30 occurrences
            ['noun', 'noun', 'noun', 'noun', 'verb', 'adverb', 'noun'],  # 30 occurrences
            ['noun', 'noun', 'noun', 'verb', 'verb', 'noun', 'verb'],  # 29 occurrences
            ['noun', 'noun', 'noun', 'noun', 'noun', 'adverb', 'verb'],  # 29 occurrences
            ['noun', 'noun', 'noun', 'noun', 'noun', 'adverb', 'noun'],  # 29 occurrences
            ['adverb', 'noun', 'noun', 'verb', 'verb', 'noun', 'noun'],  # 29 occurrences
            ['noun', 'noun', 'noun', 'verb', 'noun', 'noun', 'verb'],  # 29 occurrences
            ['adverb', 'noun', 'noun', 'noun', 'verb', 'adverb', 'verb'],  # 28 occurrences
        ],
        8: [  # 1045084 cases
            ['noun', 'noun', 'noun', 'noun', 'verb', 'verb', 'noun', 'noun'],  # 8 occurrences
            ['noun', 'noun', 'noun', 'noun', 'noun', 'verb', 'noun', 'noun'],  # 8 occurrences
            ['noun', 'noun', 'adverb', 'noun', 'verb', 'verb', 'adverb', 'noun'],  # 8 occurrences
            ['noun', 'noun', 'adverb', 'noun', 'noun', 'adverb', 'adverb', 'noun'],  # 8 occurrences
            ['noun', 'noun', 'adverb', 'noun', 'noun', 'verb', 'adverb', 'noun'],  # 8 occurrences
            ['noun', 'noun', 'noun', 'noun', 'verb', 'verb', 'adverb', 'noun'],  # 8 occurrences
            ['noun', 'noun', 'noun', 'noun', 'verb', 'adverb', 'adverb', 'noun'],  # 8 occurrences
            ['noun', 'noun', 'adverb', 'noun', 'verb', 'adverb', 'adverb', 'noun'],  # 8 occurrences
            ['noun', 'noun', 'noun', 'noun', 'verb', 'adverb', 'noun', 'noun'],  # 8 occurrences
            ['noun', 'noun', 'noun', 'noun', 'noun', 'adverb', 'noun', 'noun'],  # 8 occurrences
            ['verb', 'adverb', 'adverb', 'noun', 'verb', 'adverb', 'adverb', 'noun'],  # 7 occurrences
            ['noun', 'noun', 'adverb', 'noun', 'noun', 'adverb', 'noun', 'noun'],  # 7 occurrences
            ['noun', 'noun', 'adverb', 'noun', 'verb', 'noun', 'adverb', 'noun'],  # 7 occurrences
            ['noun', 'noun', 'noun', 'noun', 'verb', 'adverb', 'adverb', 'verb'],  # 7 occurrences
            ['noun', 'noun', 'noun', 'noun', 'verb', 'adverb', 'noun', 'verb'],  # 7 occurrences
            ['noun', 'adverb', 'noun', 'noun', 'noun', 'adverb', 'noun', 'noun'],  # 7 occurrences
            ['noun', 'noun', 'noun', 'noun', 'noun', 'adverb', 'adverb', 'noun'],  # 7 occurrences
            ['noun', 'noun', 'adverb', 'noun', 'verb', 'noun', 'adverb', 'verb'],  # 7 occurrences
            ['adverb', 'noun', 'adverb', 'noun', 'noun', 'verb', 'adverb', 'noun'],  # 7 occurrences
            ['verb', 'adverb', 'noun', 'noun', 'noun', 'adverb', 'noun', 'noun'],  # 7 occurrences
        ],
        9: [  # 1694832 cases
            ['noun', 'noun', 'noun', 'noun', 'noun', 'verb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['adverb', 'noun', 'noun', 'noun', 'verb', 'adverb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['noun', 'noun', 'verb', 'noun', 'noun', 'verb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['noun', 'noun', 'verb', 'noun', 'adverb', 'verb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['noun', 'noun', 'noun', 'noun', 'verb', 'preposition', 'noun', 'noun', 'noun'],  # 6 occurrences
            ['verb', 'noun', 'noun', 'verb', 'adverb', 'verb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['adverb', 'noun', 'noun', 'noun', 'adverb', 'verb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['noun', 'noun', 'noun', 'noun', 'adverb', 'verb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['noun', 'noun', 'noun', 'noun', 'verb', 'adverb', 'noun', 'noun', 'noun'],  # 6 occurrences
            ['adverb', 'adverb', 'verb', 'noun', 'noun', 'verb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['adverb', 'noun', 'verb', 'noun', 'noun', 'verb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['noun', 'adverb', 'verb', 'noun', 'noun', 'verb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['adverb', 'noun', 'noun', 'noun', 'verb', 'adverb', 'noun', 'noun', 'noun'],  # 6 occurrences
            ['adverb', 'noun', 'verb', 'noun', 'adverb', 'verb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['adverb', 'noun', 'noun', 'noun', 'noun', 'verb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['pronoun', 'noun', 'verb', 'noun', 'adverb', 'verb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['noun', 'noun', 'noun', 'noun', 'verb', 'adverb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['noun', 'adverb', 'noun', 'noun', 'noun', 'verb', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['noun', 'noun', 'noun', 'noun', 'verb', 'preposition', 'verb', 'noun', 'noun'],  # 6 occurrences
            ['adverb', 'adverb', 'noun', 'noun', 'noun', 'verb', 'verb', 'noun', 'noun'],  # 6 occurrences
        ],
    }

    @classmethod
    def limmerick(cls, index):
        return cls(index,
            'A -^--^--^ 3:6\n' +
            'A -^--^--^ 3:6\n' +
            'B -^--^- 1:3\n' +
            'B -^--^- 1:3\n' +
            'A -^--^--^ 3:6\n'
        )

    def __init__(self, index, pattern='A -^--^--^--^ 2:5\nB -^--^--^ 1:3\nA -^--^--^--^ 2:5\nB -^--^--^ 1:3\n', tries_per_line=50):
        self.pattern = pattern
        self.lines = ''
        self.stresses = ''
        self.types = ''

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

        def generate_line(word_stresses, word_types, line_rhyme):
            words = list()

            for i in range(len(word_stresses) - 1):
                word = Word.choice(index.get_words(word_stresses[i], word_types[i]))
                if not word:
                    return None
                words.append(word)

            word = Word.choice(index.get_words(word_stresses[-1], word_types[-1], line_rhyme))
            if not word:
                return None
            words.append(word)
            return words

        rhymes = dict()
        for line in pattern.strip().split('\n'):
            line_rhyme, line_stress, line_words = line.split(' ')
            min_words, max_words = map(int, line_words.split(':'))

            tries = tries_per_line
            while True:
                tries -= 1
                if not tries:
                    raise Exception('could not generate line')

                word_stresses = random.choice(list(splits_variant(line_stress, min_words, max_words)))
                word_types = random.choice(self.line_patterns[len(word_stresses)])
                words = generate_line(word_stresses, word_types, rhymes.get(line_rhyme))

                if not words:
                    continue
                else:
                    rhymes[line_rhyme] = words[-1].rhyme

                    self.lines += ' '.join(map(lambda word: word.text, words)) + '\n'
                    self.stresses += ' '.join(word_stresses) + '\n'
                    self.types += ' '.join(word_types) + '\n'
                    break

    def __repr__(self):
        return self.lines

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)7s - %(message)s')

    # facade = WictionaryFacade()
    index = PoetryIndex()
    print Poem.limmerick(index)

    # print Poem(index, 'a --^ 3:3\n'*4)
    # print
    # print Poem(index, 'a --^ 3:3\n'*4)
    # print
    # print Poem(index, 'a --^--^ 3:3\n'*3)
    # print
    # print Poem(index, 'a --^--^ 3:3\n'*3)