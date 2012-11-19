import cmd
import os
import sys
import math
from pippi import dsp
from pippi import param
from pippi import rt
import alsaaudio
import time
import json
import multiprocessing as mp
from termcolor import colored

class Pippi(cmd.Cmd):
    """ Pippi Console 
    """

    prompt = 'pippi: '
    intro = 'Pippi Console'

    cc = {} 
    vid = 0

    def __init__(self):
        cmd.Cmd.__init__(self)

        # TODO: recursively merge config files
        # Allow for reloading / loading from console
        config = open('config/global.json')
        self.config = json.load(config)

        config = open('config/suite.json')
        self.config.update(json.load(config))

        self.bpm = self.config['bpm']

        self.server = mp.Manager()
        self.buffers = self.server.Namespace()
        self.params = self.server.Namespace()

        self.voice_id = str(0)

        self.tick = mp.Event()

        self.grid = mp.Process(target=rt.grid, args=(self.tick, self.bpm))
        self.grid.start()

        self.cc = []

    def play(self, params):
        # Generator scripts expect a simple dict in 
        #   { param: value } 
        # format. Type conversions and range checks should 
        # always be done before being passed into the generator.
        #
        # Malkovitch Malkovitch param param
        params.bpm = self.bpm
        params = { param: params.get(param) for (param, value) in params.data.iteritems() }

        for param in params['generator']['params']:
            if param not in params:
                params[param] = params['generator']['params'][param]

        if 'bpm' not in params:
            params['bpm'] = self.bpm

        params.pop('device')

        try:
            # Increment voice id and print voice information. TODO: pretty print & abstract
            self.voice_id = str(int(self.voice_id) + 1)
            print self.voice_id, self.format_params(params)

            # Allocate a new shared voice dict to store generator params, and audio
            # data for the render process. (Render processes are spawned on demand by 
            # the voice's playback process.)
            #
            # Voices are stored in a shared namespace (self.voices) and keyed by id.

            #voice = {'snd': '', 'next': '', 'loop': True, 'tvol': 1.0, 'params': params}
            setattr(self.buffers, self.voice_id, '')
            setattr(self.params, self.voice_id, params)

            # Import the generator as a python module and spawn a playback 
            # process from rt.out, passing in the generator's play method 
            # which will be run from within a render process - spawned on demand 
            # by the voice's playback process. Sheesh.
            #
            # Generator scripts are stored in the 'orc' directory for now.

            generator = 'orc.' + params.get('generator')['name']
            generator = __import__(generator, globals(), locals(), ['play'])
            playback_process = mp.Process(target=rt.out, args=(generator.play, self.buffers, self.params, self.voice_id, self.tick))
            playback_process.start()

        except ImportError:
            # We'll get an ImportError exception here if a generator has been registered 
            # in the json config file and there is no matching generator script in the orc/ directory.

            print 'invalid generator'

    def do_c(self, cmd):
        cmd = cmd.split(' ')
        t = cmd[0]
        cmd.pop(0)
        self.cc += [ t ]
        print self.cc

    def do_ss(self, cmd):
        gen = 'all'

        cmds = cmd.split(' ')
        if cmds[0] != '' and cmds[0] != 'all':
            gen = cmds

        for voice_id in range(1, int(self.voice_id) + 1):
            voice_id = str(voice_id)
            if hasattr(self.params, voice_id):
                params = getattr(self.params, voice_id)

                if params['generator']['name'] in gen or gen == 'all':
                    params['loop'] = False
                    setattr(self.params, voice_id, params)

    def do_s(self, cmd):
        cmds = cmd.split(' ')

        for cmd in cmds:
            voice_id = cmd.strip() 
            if hasattr(self.params, voice_id):
                params = getattr(self.params, voice_id)
                params['loop'] = False
                setattr(self.params, voice_id, params)

    def do_vv(self, cmd):
        cmds = cmd.split(' ')

        for voice_id in range(1, int(self.voice_id) + 1):
            self.setvol(str(voice_id), cmds[1], cmds[0])

    def do_v(self, cmd):
        cmds = cmd.split(' ')
        self.setvol(cmds[0], cmds[1])

    def setvol(self, voice_id, volume, generator='a'):
        if hasattr(self.params, voice_id):
            params = getattr(self.params, voice_id)
            if generator == params['generator']['name'] or generator == 'a':
                params['target_volume'] = float(volume) / 100.0
                setattr(self.params, voice_id, params)

    def do_i(self, cmd=[]):
        for voice_id in range(1, int(self.voice_id) + 1):
            voice_id = str(voice_id)
            if hasattr(self.params, voice_id):
                params = getattr(self.params, voice_id)
                print voice_id, self.format_params(params)

    def format_params(self, params=[]):
        # TODO: translate types & better formatting
        param_string = ''
        for param in params:
            value = params[param]['name'] if param == 'generator' else params[param]
            param_string += colored(str(param)[0:3] + ': ', 'cyan') + colored(str(value), 'yellow') + ' '
        
        return param_string

    def do_p(self, cmd):
        if cmd in self.config['presets']:
            cmd = self.config['presets'][cmd]

            for c in cmd:
                if len(c) > 2:
                    self.default(c)
                    dsp.delay(0.1)

    def default(self, cmd):
        # Break comma separated commands
        # into a list of command strings
        cmds = cmd.strip().split(',')

        # For each command string, unpack and load
        # into a param.Param instance based on 
        # current json config rules. 
        #
        # So:
        #   sh o:3
        #
        # Could become:
        #   { 'generator': 'shine', 'octave': {'value': 3, 'type': 'integer'} }
        # 
        # And:
        #   dr h:1.2.3.4 t:4b wf:tri n:eb.g
        # 
        # Could become:
        #   {
        #       'generator': 'drone',
        #       'harmonics': {'value': '1.2.3.4', 'type': 'integer-list'},
        #       'length': {'value': '4b', 'type': 'frame'},
        #       'waveform': {'value': 'tri'},
        #       'notes': {'value': 'eb.g', 'type': 'note-list'}
        #   }
        # 
        # For a complete list of reserved words and built-in types please 
        # refer to the documentation I haven't written yet. Oh, bummer.
        # In the meantime, the patterns in param.py should help a little.
        #
        # Finally pass to self.play() to spawn render and playback processes.

        for cmd in cmds:

            params = param.unpack(cmd, self.config)
            generator = params.get('generator')

            if generator is False:
                print 'invalid generator'
            else:
                self.play(params)

    def do_EOF(self, line):
        return True

    def postloop(self):
        pass

if __name__ == '__main__':
        # Create console
        console = Pippi()

        # Start looping command prompt
        console.cmdloop()
