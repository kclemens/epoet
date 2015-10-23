import webapp2
import boxes
import logging


class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/html'
        self.response.write(open('box.html').read())

class AbstractService(webapp2.RequestHandler):

    def get(self):
        lat = self.request.get('lat')
        lon = self.request.get('lon')
        name = self.request.get('name').split()

        if name or (lat and lon):
            if lat and lon:
                name = self.rhyme_index.to_box_name(float(lat), float(lon))

            box = self.rhyme_index.from_box_name(name)
            lat, lon = box.centroid()

            self.response.headers['Content-Type'] = 'application/json'
            self.response.write('{{"name":"{}","lat":{}, "lon":{}, "top":{}, "left":{},"bottom":{},"right":{}}}'.format(
                ' '.join(name), lat, lon, box.max_x, box.min_y, box.min_x, box.max_y))

        else:
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('you need to specify lat and lon or name parameters'.format(lat, lon))
            self.response.set_status(400)


class RhymeService(AbstractService):
    rhyme_index = boxes.BoxIndex.from_file('rhyme_box_index.json.gz')

class SyllablesService(AbstractService):
    rhyme_index = boxes.BoxIndex.from_file('syllables_box_index.json.gz')

app = webapp2.WSGIApplication([
    ('/', MainPage),
    webapp2.Route(r'/rhyme', handler=RhymeService, methods=['GET']),
    webapp2.Route(r'/syllables', handler=SyllablesService, methods=['GET']),
], debug=True)