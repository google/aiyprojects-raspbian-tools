# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Server commands and client messages defined according to
http://json-schema.org/
"""

CLIENT_MESSAGES = {
    'definitions': {
        'stdout_message': {
            'type': 'object',
            'properties': {
                'type': {
                   'type': 'string',
                   'enum': ['stdout']
                },
                'data': {
                   'type': 'string',
                }
            },
            'required': ['type', 'data']
        },
        'stderr_message': {
            'type': 'object',
            'properties': {
                'type': {
                   'type': 'string',
                   'enum': ['stderr']
                },
                'data': {
                   'type': 'string',
                }
            },
            'required': ['type', 'data']
        },
        'exit_message' : {
            'type': 'object',
            'properties': {
                'type': {
                   'type': 'string',
                   'enum': ['exit']
                },
                'code': {
                   'type': 'number',
                }
            },
            'required': ['type', 'code']
        }
    },

    'allOf': [
        {
            'properties': {
                'type': {
                    'description': 'Message type.',
                    'type': 'string',
                    'enum': ['stdout', 'stderr', 'exit']
                },
            },
            'required': ['type']
        },
        {
            'anyOf': [
                { '$ref': '#/definitions/stdout_message' },
                { '$ref': '#/definitions/stderr_message' },
                { '$ref': '#/definitions/exit_message' },
            ]
        }
    ]
}

SERVER_COMMANDS = {
    'definitions': {
        'run_command': {
            'type': 'object',
            'properties': {
                 'type': {
                    'type': 'string',
                    'enum': ['run']
                 },
                 'args': {
                     'description': 'Command line arguments.',
                     'type': 'array',
                     'items': {
                         'type': 'string'
                     }
                 },
                 'chunk_size': {
                     'description': 'Read buffer size.',
                     'type': 'number',
                     'minimum': 0
                 },
                 'stdout': {
                    'type': 'string',
                    'enum': ['null', 'pipe']
                 },
                 'stderr': {
                    'type': 'string',
                    'enum': ['null', 'pipe', 'stdout']
                 },
                 'files': {
                    'type': 'object'
                 },
                 'env': {
                    'type': 'object'
                 }
             },
             'required': ['type']
        },
        'signal_command': {
              'type': 'object',
              'properties': {
                  'type': {
                      'type': 'string',
                      'enum': ['signal'],
                  },
                  'signum': {
                      'description': 'http://man7.org/linux/man-pages/man7/signal.7.html',
                      'type': 'number',
                      'minimum': 1,
                      'maximum': 32
                  }
              },
              'required': ['type', 'signum']
        },
        'stdin_command': {
              'type': 'object',
              'properties': {
                  'type': {
                      'type': 'string',
                      'enum': ['stdin'],
                  },
                  'data': {
                      'type': 'string',
                  }
              },
              'required': ['type', 'data']
        }
    },

    'allOf': [
        {
            'properties': {
                'type': {
                    'description': 'Command type.',
                    'type': 'string',
                    'enum': ['run', 'signal', 'stdin']
                },
            },
            'required': ['type']
        },
        {
            'anyOf': [
                { '$ref': '#/definitions/run_command' },
                { '$ref': '#/definitions/signal_command' },
                { '$ref': '#/definitions/stdin_command' },
            ]
        }
    ]
}
