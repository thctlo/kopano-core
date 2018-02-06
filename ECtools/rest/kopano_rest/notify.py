import base64
import codecs
import falcon
import json
import uuid
try:
    from queue import Queue
except ImportError:
    from Queue import Queue
from threading import Thread

import kopano

from . import utils

PREFIX = '/api/gc/v0'

def _user(req):
    auth_header = req.get_header('Authorization')
    userid = req.get_header('X-Kopano-UserEntryID')
    if auth_header:
        user, passwd = codecs.decode(codecs.encode(auth_header[6:], 'ascii'), 'base64').split(b':')
        return SERVER.user(codecs.decode(user, 'utf8'))
    elif userid:
        return SERVER.user(userid=userid)

# TODO don't block on sending updates
# TODO restarting app/server
# TODO handshake/call webhook

class Processor(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True

    def run(self):
        while True:
            store, notification = QUEUE.get()
            print('call webhook!', store, notification)

class Sink:
    def __init__(self, store):
        self.store = store

    def update(self, notification):
        QUEUE.put((self.store, notification))

def _get_folder(store, resource):
    resource = resource.split('/')
    if (len(resource) == 4 and \
        resource[0] == 'me' and resource[1] == 'mailFolders' and resource[3] == 'messages'):
        folderid = resource[2]
    return utils._folder(store, folderid)

class SubscriptionResource:
    def on_post(self, req, resp):
        user = _user(req)
        store = user.store
        fields = json.loads(req.stream.read().decode('utf-8'))
        folder = _get_folder(store, fields['resource'])

        # TODO store-level, hierarchy.. ?

        sink = Sink(store)
        folder.subscribe(sink)

        id_ = str(uuid.uuid4())
        subscription = {
            'id': id_,
            'resource': fields['resource'],
        }
        SUBSCRIPTIONS[id_] = (subscription, sink)

        resp.content_type = "application/json"
        resp.body = json.dumps(subscription, indent=2, separators=(',', ': '))

    def on_delete(self, req, resp, subscriptionid=None):
        user = _user(req)
        store = user.store
        fields = json.loads(req.stream.read().decode('utf-8'))

        subscription, sink = SUBSCRIPTIONS[fields['id']]
        folder = _get_folder(store, subscription['resource'])

        folder.unsubscribe(sink)

SERVER = kopano.Server(notifications=True)
SUBSCRIPTIONS = {}
QUEUE = Queue()

subscriptions = SubscriptionResource()
app = falcon.API()
app.add_route(PREFIX+'/subscriptions', subscriptions)
app.add_route(PREFIX+'/subscriptions/{subscriptionid}', subscriptions)

Processor().start()
