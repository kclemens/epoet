import logging
import collections
import random
import socket
import time

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

class Word(object):
    def __init__(self, line, phones):
        '''d'artagnan D AH0 R T AE1 NG Y AH0 N # foreign french'''

        logging.debug('parsing word from line "%s"', line)

        if '#' in line:
            line = line[:line.find('#')]

        tokens = line.split()
        if tokens[0][-1] == ')':
            self.text = tokens[0][:-3]
        else:
            self.text = tokens[0]
        logging.debug('got text %s', self.text)

        phones.validate(tokens[1:])

        last_stress_index = 0
        for i, token in enumerate(tokens[1:]):
            if len(token) == 3 and int(token[2]) > 0:
                last_stress_index = i
        self.rhyme = tokens[1:][last_stress_index:]
        self.rhyme = map(lambda token: token[:2] if len(token) == 3 else phones.get_type(token), self.rhyme)
        self.rhyme = ':'.join(self.rhyme)
        logging.debug('got rhyme %s', self.rhyme)

        self.stress = filter(lambda token: len(token) == 3, tokens[1:])
        self.stress = map(lambda token: '^' if int(token[2]) > 0 else '-', self.stress)
        self.stress = ''.join(self.stress)
        logging.debug('got stress %s', self.stress)

        self.sound = ':'.join(tokens[1:])
        logging.debug('got sound %s', self.sound)

    def __repr__(self):
        return '|{:^50s} | {:^70s} | {:^10s} | {:^50s}|'.format(self.text, self.sound, self.stress, self.rhyme)

class PoetryIndex(object):
    @classmethod
    def from_file(cls, phones, filename='../cmudict/cmudict.dict'):
        logging.info('loading words from "%s"', filename)

        def lines():
            for line in open(filename):
                line = line.strip()
                word = Word(line, phones)
                logging.debug('adding %s', word)
                yield word

        return cls(lines())

    def __init__(self, words):
        self.stresses = dict()
        self.rhymes = dict()

        i = 0
        for i, word in enumerate(words):
            self.rhymes.setdefault(word.rhyme, set()).add(word)
            self.stresses.setdefault(word.stress, set()).add(word)

        logging.info('got %s words.', i)

    def __repr__(self):
        counter = collections.Counter()
        for rhyme, words in self.rhymes.items():
            counter[rhyme] += len(words)

        result = 'PoetryIndex with {} rhymes and {} stress patterns:\n'.format(len(self.rhymes), len(self.stresses))

        for rhyme, count in counter.most_common(3):
            words = self.rhymes.get(rhyme)
            result += 'five out of {} words with rhyme {}\n'.format(count, rhyme)
            for word in random.sample(words, min(5, count)):
                result += '{}\n'.format(word)

        counter = collections.Counter()
        for stress, words in self.stresses.items():
            counter[stress] += len(words)

        for stress, count in counter.most_common(3):
            words = self.stresses.get(stress)
            result += 'five out of {} words with stress {}\n'.format(count, stress)
            for word in random.sample(words, min(5, count)):
                result += '{}\n'.format(word)

        return result

    def next_word(self, stress):
        result = map(lambda i: stress[0:i], range(1, len(stress) + 1))  # all stess prefixes
        result = map(lambda stress_prefix: self.stresses.get(stress_prefix, set()), result) # their words
        result = set().union(*result)  # in one set

        if not result:
            return None

        return random.choice(list(result))  # pick at random

    def last_word(self, stress, rhyme_word=None):
        words = self.stresses.get(stress, set())
        if rhyme_word:
            words &= self.rhymes.get(rhyme_word.rhyme, set())

        if rhyme_word in words:
            words.remove(rhyme_word)

        if words:
            return random.choice(list(words))
        else:
            return None

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

    def __init__(self, title, index, lines='A-^--^- B-^--^ A-^--^- B-^--^'):
        self.lines = list()
        self.title = title

        rhymes = dict()
        for line in lines.split():
            while True:
                rhyme = line[0]
                stress = line[1:]
                max_last_word_length = len(stress) / 3
                generated_line = list()

                while len(stress) > max_last_word_length:
                    next_word = index.next_word(stress)
                    if next_word:
                        generated_line .append(next_word)
                        stress = stress[len(next_word.stress):]
                    else:
                        logging.warning('failed to generate line "%s"', line)
                        logging.warning('got so far: %s', ' '.join(map(lambda x:x.text, generated_line )))
                        logging.warning('remaining stress: %s', stress)
                        raise Exception()

                next_word = index.last_word(stress, rhymes.get(rhyme))
                if next_word:
                    generated_line .append(next_word)
                    rhymes[rhyme] = next_word

                    self.lines.append(generated_line )
                    break
                else:
                    logging.debug('failed to generate line "%s"', line)
                    logging.debug('got so far: %s', ' '.join(map(lambda x:x.text, generated_line )))
                    logging.debug('required rhyme: %s', rhymes.get(rhyme))
                    logging.debug('remaining stress: %s', stress)

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

    import sys
    if len(sys.argv) > 1:
        base_path = sys.argv[1]
        index = PoetryIndex.from_file(Phones.from_file(base_path+'/cmudict.phones'), base_path+'/cmudict.dict')
    else:
        # default location: cmudict next to epoet
        index = PoetryIndex.from_file(Phones.from_file())

    print Poem('a beautiful lady', index, 'A-^-^-^ N-^-^-^ N-^-^-^ A-^-^-^')
    print Poem.limmerick('limeric', index)


