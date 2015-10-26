import webapp2
import boxes


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

            try:
                box = self.rhyme_index.from_box_name(name)
            except ValueError:
                self.response.headers['Content-Type'] = 'text/plain'
                self.response.write('you have specified an invalid box name: {}'.format(name))
                self.response.set_status(400)
                return

            lat, lon = box.centroid()

            self.response.headers['Content-Type'] = 'application/json'
            self.response.write('{{"name":"{}","lat":{:f}, "lon":{:f}, "top":{:f}, "left":{:f},"bottom":{:f},"right":{:f}}}'.format(
                ' '.join(name), lat, lon, box.max_lat, box.min_lon, box.min_lat, box.max_lon))

        else:
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('you need to specify lat and lon or name parameters')
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