'''
Functions and objects related to importing Minecraft models to Blender.
'''
from __future__ import annotations

import math
from typing import cast, Dict, List, Optional, Any, Tuple, Set

import numpy as np

import bpy_types
import mathutils
import bpy

from .common import MINECRAFT_SCALE_FACTOR, CubePolygons, CubePolygon
from .uv import CoordinatesConverter
from .exception import (
    InvalidDictPathException, FileIsNotAModelException,
    ImportingNotImplementedError)
from .json_tools import get_path

def _assert(expr: bool, msg: str = ''):
    '''Used in this module to raise exceptions based on condition.'''
    if not expr:
        raise FileIsNotAModelException(msg)

def _assert_is_vector(
        name: str, obj: Any, length: int, types: Tuple, json_path: List
    ) -> None:
    '''
    Asserts that object is an aray of specific length with specyfic type of
    items.
    '''
    _assert(isinstance(obj, list), f'{json_path}::{name} is not a list')
    _assert(
        len(obj) == length,
        f'{json_path}::{name} has invalid length {len(obj)} != {length}')
    _assert(
        all([isinstance(i, types) for i in obj]),
        f'{json_path}::{name} is not instance of List[{types}]')

def _assert_has_required_keys(
        what: str, has_keys: Set, required_keys: Set, json_path: List):
    '''Asserts that object has required keys.'''
    missing_keys = required_keys - has_keys
    if len(missing_keys) != 0:
        raise FileIsNotAModelException(
            f'{json_path}::{what} is missing properties: {missing_keys}')

def _assert_has_accepted_keys_only(
        what: str, has_keys: Set, accepted_keys: Set, json_path: List):
    '''Asserts that object has only keys from accepted set.'''
    additional_keys = has_keys - accepted_keys
    if len(additional_keys) != 0:
        raise FileIsNotAModelException(
            f'{json_path}::{what} has unexpected properties: {additional_keys}')

def _assert_is_type(
        name: str, obj: Any, types: Tuple, json_path: List):
    '''Asserts that object is instance of specyfic type'''
    if not isinstance(obj, types):
        raise FileIsNotAModelException(
            f'{json_path}::{name} is not an instance of {types}')

def pick_version_parser(parsers: Tuple[str, ...], version: str):
    '''
    Out of known list of parser names for different format versions picks the
    earliest possible format_version greater or equal to the version.
    '''
    def to_tuple(version: str) -> Tuple[int]:
        try:
            return tuple(  # type: ignore
                map(lambda a: int(a), version.split('.')))
        except:
            raise FileIsNotAModelException(
                f'Unable to parse format version number: {version}')

    t_parsers = [to_tuple(parser) for parser in parsers]
    t_parsers.sort(reverse=True)
    t_version = to_tuple(version)

    best_choice = None
    for t_parser in t_parsers:
        if t_parser <= t_version:
            best_choice = t_parser
            break
    if best_choice is None:
        raise FileIsNotAModelException(
            f'Unsuported format version: {version}')
    return '.'.join([str(i) for i in best_choice])


class ModelLoader:
    '''
    Interface loads model from a dictionary that represents the model.
    Fills missing/optional data with default values.
    '''
    def __init__(self, data: Dict, geometry_name: str = ""):
        self.data = data
        self.format_version = self._load_format_version(data)
        geometry, geometry_path = self._load_geometry(
            geometry_name, self.data)

        self.description: Dict = self._load_description(
            geometry, geometry_path)
        self.bones: List = self._load_bones(
            geometry['bones'],  geometry_path + ['bones'])
    
    def _load_format_version(self, data: Dict) -> str:
        '''
        Returns the version of the model from JSON file loaded into data.

        - `data: Dict` - loaded JSON file into model.
        '''
        _assert_has_required_keys(
            'model file', set(data.keys()), {'format_version'}, [])
        parser_version = pick_version_parser(
            ('1.12.0', '1.8.0'), data['format_version'])
        if parser_version == '1.12.0':
            _assert_has_required_keys(
                'model file', set(data.keys()),
                    
                {'minecraft:geometry', 'format_version'},
                [])
            _assert_has_accepted_keys_only(
                'model file', set(data.keys()),
                {'minecraft:geometry', 'format_version', 'cape'}, [])
            if 'cape' in data.keys():
                raise ImportingNotImplementedError('cape', [])
            return data['format_version']
        elif parser_version == '1.8.0':
            # All geometries must start with geometry.
            for k in data.keys():  # key must be string because its from json
                _assert(
                    (
                        k.startswith('geometry.') or
                        k in ['debug', 'format_version']
                    ),
                    f'{[]}::{k} is invalid geometry name (it should start '
                    'with "geometry."'
                )
            if 'debug' in data.keys():
                raise ImportingNotImplementedError('debug', [])
            return data['format_version']
        else:
            raise FileIsNotAModelException('Unsuported format version')

    def _load_geometry(
            self, geometry_name: str, data: Any) -> Tuple[Dict, List]:
        '''
        Finds and returns geometry with specific name from list of gemoeties
        from JSON file with models. Returns the geometry dictionary with added
        all of the missing values and the JSON path to the geometry.

        - `geometry_name: str` - the name of geometry
        - `data: Any` - root object of the json
        '''
        parser_version = pick_version_parser(
            ('1.12.0', '1.8.0'), self.format_version)
        if parser_version == '1.12.0':
            geometries = data['minecraft:geometry']
            path: List = ['minecraft:geometry']
            _assert_is_type('geometries', geometries, (list,), path)
            for i, geometry in enumerate(geometries):
                path = ['minecraft:geometry', i]
                _assert_is_type('gometry', geometry, (dict,),
                    path)
                _assert_has_required_keys(
                    'geometry', set(geometry.keys()), {'description', 'bones'},
                    path)
                _assert_has_accepted_keys_only(
                    'geometry', set(geometry.keys()), {'description', 'bones'},
                    path)
                desc = geometry['description']
                if 'identifier' not in desc:
                    raise FileIsNotAModelException(
                        f'{path}::description is missing identifier')
                identifier = desc['identifier']
                if identifier == geometry_name or geometry_name == '':
                    return geometry, path
            raise ValueError(f'Unable to find geometry called geometry.{geometry_name}')
        elif parser_version == '1.8.0':
            geometries = data
            path = []
            _assert_is_type('geometries', geometries, (dict,), path)
            for k, geometry in geometries.items():
                if k in ['format_version', 'debug']:
                    continue
                path = [k]
                _assert_is_type('gometry', geometry, (dict,),
                    path)
                _assert_has_accepted_keys_only(
                    'geometry', set(geometry.keys()),
                    {
                        "debug", "visible_bounds_width",
                        "visible_bounds_height", "visible_bounds_offset",
                        "texturewidth", "textureheight", "cape", "bones"
                    }, path)
                identifier = k
                if identifier == geometry_name or geometry_name == '':
                    return geometry, path
            raise ValueError(f'Unable to find geometry called geometry.{geometry_name}')
        else:
            raise FileIsNotAModelException(f'Unsuported format version: {self.format_version}')

    def _load_description(self, geometry: Any, geometry_path: List) -> Dict:
        '''
        Returns the description of the geometry.

        - `geometry: Any` - the geometry with description
        - `geometry_path: List` - the JSON path to the geometry (for error
          messages)
        '''
        result = {
            "texture_width" : 64,
            "texture_height" : 64,
            "visible_bounds_offset" : [0, 0, 0],
            "visible_bounds_width" : 1,
            "visible_bounds_height": 1
        }
        parser_version = pick_version_parser(
            ('1.12.0', '1.8.0'), self.format_version)
        if parser_version == '1.12.0':
            desc = geometry['description']
            path = geometry_path + ['description']

            _assert_has_required_keys(
                'description', set(desc.keys()), {'identifier'}, path)
            acceptable_keys = {
                    'identifier', 'texture_width', 'texture_height',
                    'visible_bounds_offset', 'visible_bounds_width',
                    'visible_bounds_height'}
            _assert_has_accepted_keys_only(
                'description', set(desc.keys()), acceptable_keys, path)

            _assert_is_type(
                'identifier', desc['identifier'], (str,),
                geometry_path + ['identifier'])
            result['identifier'] = desc['identifier']
            if 'texture_width' in desc:
                _assert_is_type(
                    'texture_width', desc['texture_width'], (int, float),
                    geometry_path + ['texture_width'])
                result['texture_width'] = int(desc['texture_width'])
            if 'texture_height' in desc:
                _assert_is_type(
                    'texture_height', desc['texture_height'], (int, float),
                    geometry_path + ['texture_height'])
                result['texture_height'] = int(desc['texture_height'])
            if 'visible_bounds_offset' in desc:
                _assert_is_vector(
                    'visible_bounds_offset', desc['visible_bounds_offset'], 3,
                    (int, float), geometry_path + ['visible_bounds_offset'])
                result['visible_bounds_offset'] = desc['visible_bounds_offset']
            if 'visible_bounds_width' in desc:
                _assert_is_type(
                    'visible_bounds_width', desc['visible_bounds_width'],
                    (int, float), geometry_path + ['visible_bounds_width'])
                result['visible_bounds_width'] = desc['visible_bounds_width']
            if 'visible_bounds_height' in desc:
                _assert_is_type(
                    'visible_bounds_height', desc['visible_bounds_height'],
                    (int, float), geometry_path + ['visible_bounds_height'])
                result['visible_bounds_height'] = desc['visible_bounds_height']
            return result
        elif parser_version == '1.8.0':
            desc = geometry
            path = geometry_path

            acceptable_keys = {
                        "debug", "visible_bounds_width",
                        "visible_bounds_height", "visible_bounds_offset",
                        "texturewidth", "textureheight", "cape", "bones"}
            _assert_has_accepted_keys_only(
                'geometry', set(desc.keys()), acceptable_keys, path)

            _assert_is_type(
                'identifier', path[-1], (str,),
                geometry_path + ['identifier'])
            result['identifier'] = path[-1]
            if 'debug' in desc:
                _assert_is_type(
                    'debug', desc['debug'], (bool,),
                    geometry_path + ['debug'])
                raise ImportingNotImplementedError('debug', path + ['debug'])
            if 'texturewidth' in desc:
                _assert_is_type(
                    'texturewidth', desc['texturewidth'], (int, float),
                    geometry_path + ['texturewidth'])
                # texture_width not texturewidth (not a bug!!!)
                result['texture_width'] = int(desc['texturewidth'])
            if 'textureheight' in desc:
                _assert_is_type(
                    'textureheight', desc['textureheight'], (int, float),
                    geometry_path + ['textureheight'])
                # texture_height not textureheight (not a bug!!!)
                result['texture_height'] = int(desc['textureheight'])
            if 'visible_bounds_offset' in desc:
                _assert_is_vector(
                    'visible_bounds_offset', desc['visible_bounds_offset'], 3,
                    (int, float), geometry_path + ['visible_bounds_offset'])
                result['visible_bounds_offset'] = desc['visible_bounds_offset']
            if 'visible_bounds_width' in desc:
                _assert_is_type(
                    'visible_bounds_width', desc['visible_bounds_width'],
                    (int, float), geometry_path + ['visible_bounds_width'])
                result['visible_bounds_width'] = desc['visible_bounds_width']
            if 'visible_bounds_height' in desc:
                _assert_is_type(
                    'visible_bounds_height', desc['visible_bounds_height'],
                    (int, float), geometry_path + ['visible_bounds_height'])
                result['visible_bounds_height'] = desc['visible_bounds_height']
            return result
        else:
            raise FileIsNotAModelException('Unsuported format version')

    def _load_bones(
            self, bones: Any, bones_path: List) -> List[Dict[str, Any]]:
        '''
        Returns the bones from a list of bones with added missing values.

        - `bones: Any` - list of bones
        - `bones_path: List` - path to the bones list (for error messages)
        '''
        result: List = []
        parser_version = pick_version_parser(
            ('1.12.0', '1.8.0'), self.format_version)
        if parser_version == '1.12.0' or parser_version == '1.8.0':
            _assert_is_type('bones property', bones, (list,), bones_path)
            for i, bone in enumerate(bones):
                bone_path = bones_path + [i]
                result.append(self._load_bone(bone, bone_path))
            return result
        else:
            raise FileIsNotAModelException('Unsuported format version')

    def _load_bone(self, bone: Any, bone_path: List) -> Dict[str, Any]:
        '''
        Returns a bone with added all of the missing default values of the
        properties.

        - `bone: Any` - part of the json file that has the inforation about the
          bone
        - `bone_path: List` - path to the bone (for error messages)
        '''
        result: Dict[str, Any] = {
            "parent": None,  # str
            "pivot" : [0, 0, 0],  # List[float] len=3
            "rotation" : [0, 0, 0],  # List[float] len=3
            "mirror" : False,  # bool
            "inflate": 0.0,  # float
            "debug": False,  # bool
            "render_group_id": 0,  # int >= 0
            "cubes" : [],  # List[Dict]
            "locators": {},  # Dict[...]  # TODO - parsing dict locators Dict[List or Dict]
            "poly_mesh": {},  # Dict
            "texture_meshes": []  # List[Dict]
        }
        parser_version = pick_version_parser(
            ('1.12.0', '1.8.0'), self.format_version)
        if parser_version == '1.12.0':
            _assert_is_type('bone', bone, (dict,), bone_path)


            _assert_has_required_keys(
                'bone', set(bone.keys()), {'name'}, bone_path)
            acceptable_keys = {
                'name', 'parent', 'pivot', 'rotation', 'mirror', 'inflate',
                'debug', 'render_group_id', 'cubes', 'locators', 'poly_mesh',
                'texture_meshes'}
            _assert_has_accepted_keys_only(
                'bone', set(bone.keys()), acceptable_keys, bone_path)

            if 'name' in bone:
                _assert_is_type(
                    'name', bone['name'], (str,), bone_path + ['name'])
                result['name'] = bone['name']
            if 'parent' in bone:
                _assert_is_type(
                    'parent', bone['parent'], (str,), bone_path + ['parent'])
                result['parent'] = bone['parent']
            if 'pivot' in bone:
                _assert_is_vector(
                    'pivot', bone['pivot'], 3, (int, float),
                    bone_path + ['pivot'])
                result['pivot'] = bone['pivot']
            if 'rotation' in bone:
                _assert_is_vector(
                    'rotation', bone['rotation'], 3, (int, float),
                    bone_path + ['rotation'])
                result['rotation'] = bone['rotation']
            if 'mirror' in bone:
                _assert_is_type(
                    'mirror', bone['mirror'], (bool,), bone_path + ['mirror'])
                result['mirror'] = bone['mirror']
            if 'inflate' in bone:
                _assert_is_type(
                    'inflate', bone['inflate'], (float, int),
                    bone_path + ['inflate'])
                raise ImportingNotImplementedError('inflate', bone_path + ['inflate'])
            if 'debug' in bone:
                _assert_is_type(
                    'debug', bone['debug'], (bool,), bone_path + ['debug'])
                raise ImportingNotImplementedError(
                    'debug', bone_path + ['debug'])
            if 'redner_group_id' in bone:
                _assert_is_type(
                    'redner_group_id', bone['redner_group_id'], (int, float),
                    bone_path + ['redner_group_id'])
                # int >= 0
                raise ImportingNotImplementedError(
                    'redner_group_id', bone_path + ['redner_group_id'])
            if 'cubes' in bone:
                # default mirror for cube is the bones mirror property
                result['cubes'] = self._load_cubes(
                    bone['cubes'], bone_path + ['cubes'], result['mirror'])
            if 'locators' in bone:
                result['locators'] = self._load_locators(
                    bone['locators'], bone_path + ['locators'])
            if 'poly_mesh' in bone:
                # type: dict
                raise ImportingNotImplementedError(
                    'poly_mesh', bone_path + ['poly_mesh'])
            if 'texture_meshes' in bone:
                # type: list
                raise ImportingNotImplementedError(
                    'texture_meshes', bone_path + ['texture_meshes'])
                
            return result
        elif parser_version == '1.8.0':
            _assert_is_type('bone', bone, (dict,), bone_path)

            _assert_has_required_keys(
                'bone', set(bone.keys()), {'name'}, bone_path)
            acceptable_keys = {
                'name', 'reset', 'neverRender', 'parent', 'pivot', 'rotation',
                'bind_pose_rotation', 'mirror', 'inflate', 'debug',
                'render_group_id', 'cubes', 'locators', 'poly_mesh',
                'texture_meshes'}
            _assert_has_accepted_keys_only(
                'bone', set(bone.keys()), acceptable_keys, bone_path)

            if 'name' in bone:
                _assert_is_type(
                    'name', bone['name'], (str,), bone_path + ['name'])
                result['name'] = bone['name']
            if 'reset' in bone:
                _assert_is_type(
                    'reset', bone['reset'], (bool,), bone_path + ['reset'])
                raise ImportingNotImplementedError(
                    'reset', bone_path + ['reset'])
            if 'neverRender' in bone:
                _assert_is_type(
                    'neverRender', bone['neverRender'], (bool,),
                    bone_path + ['neverRender'])
                raise ImportingNotImplementedError(
                    'neverRender', bone_path + ['neverRender'])
            if 'parent' in bone:
                _assert_is_type(
                    'parent', bone['parent'], (str,), bone_path + ['parent'])
                result['parent'] = bone['parent']
            if 'pivot' in bone:
                _assert_is_vector(
                    'pivot', bone['pivot'], 3, (int, float),
                    bone_path + ['pivot'])
                result['pivot'] = bone['pivot']
            if 'rotation' in bone:
                _assert_is_vector(
                    'rotation', bone['rotation'], 3, (int, float),
                    bone_path + ['rotation'])
                result['rotation'] = bone['rotation']
            if 'bind_pose_rotation' in bone:
                _assert_is_vector(
                    'bind_pose_rotation', bone['bind_pose_rotation'], 3,
                    (int, float), bone_path + ['bind_pose_rotation'])
                raise ImportingNotImplementedError(
                    'bind_pose_rotation', bone_path + ['bind_pose_rotation'])
            if 'mirror' in bone:
                _assert_is_type(
                    'mirror', bone['mirror'], (bool,), bone_path + ['mirror'])
                result['mirror'] = bone['mirror']
            if 'inflate' in bone:
                _assert_is_type(
                    'inflate', bone['inflate'], (float, int),
                    bone_path + ['inflate'])
                raise ImportingNotImplementedError('inflate', bone_path + ['inflate'])
            if 'debug' in bone:
                _assert_is_type(
                    'debug', bone['debug'], (bool,), bone_path + ['debug'])
                raise ImportingNotImplementedError(
                    'debug', bone_path + ['debug'])
            if 'redner_group_id' in bone:
                _assert_is_type(
                    'redner_group_id', bone['redner_group_id'], (int, float),
                    bone_path + ['redner_group_id'])
                # int >= 0
                raise ImportingNotImplementedError(
                    'redner_group_id', bone_path + ['redner_group_id'])
            if 'cubes' in bone:
                # default mirror for cube is the bones mirror property
                result['cubes'] = self._load_cubes(
                    bone['cubes'], bone_path + ['cubes'], result['mirror'])
            if 'locators' in bone:
                result['locators'] = self._load_locators(
                    bone['locators'], bone_path + ['locators'])
            if 'poly_mesh' in bone:
                # type: dict
                raise ImportingNotImplementedError(
                    'poly_mesh', bone_path + ['poly_mesh'])
            if 'texture_meshes' in bone:
                # type: list
                raise ImportingNotImplementedError(
                    'texture_meshes', bone_path + ['texture_meshes'])
            return result
        else:
            raise FileIsNotAModelException('Unsuported format version')

    def _load_cubes(
            self, cubes: Any, cubes_path: List[Any],
            default_mirror: bool) -> List[Dict[str, Any]]:
        '''
        Returns the cubes from the list of cubes with added missing values.

        - `cubes: Any` - list of cubes
        - `cubes_path: List[Any]` - path to the cubes list (for error messages)
        - `default_mirror: bool` - mirror value of a bone that owns this list
          of cubes.
        '''
        result = []
        parser_version = pick_version_parser(
            ('1.12.0', '1.8.0'), self.format_version)
        if parser_version == '1.12.0' or parser_version == '1.8.0':
            _assert_is_type('cubes property', cubes, (list,), cubes_path)
            for i, cube in enumerate(cubes):
                cube_path = cubes_path + [i]
                result.append(self._load_cube(cube, cube_path, default_mirror))
            return result
        else:
            raise FileIsNotAModelException('Unsuported format version')

    def _load_cube(
            self, cube: Any, cube_path: List,
            default_mirror: bool) -> Dict[str, Any]:
        '''
        Returns a cube with added all of the missing default values of the
        properties.

        - `cube: Any` - part of the json file that has the inforation about the
          cube
        - `cube_path: List` - path to the cube (for error messages)
        - `default_mirror: bool` - mirror value of a bone that owns this cube
        '''
        result = {
            "origin" : [0, 0, 0],  # Listfloat] len=3
            "size" : [0, 0, 0],  # Listfloat] len=3
            "rotation" : [0, 0, 0],  # Listfloat] len=3
            "pivot" : [0, 0, 0],  # Listfloat] len=3
            "inflate" : 0,  # float
            "mirror" : default_mirror,  # mirror
            "uv": [0, 0]  # List[float] len=2 or Dict  # TODO - load dictionary format
        }
        parser_version = pick_version_parser(
            ('1.12.0', '1.8.0'), self.format_version)
        if parser_version == '1.12.0':
            _assert_is_type('cube', cube, (dict,), cube_path)
            # There is no required keys {} is a valid cube
            acceptable_keys = {
                "mirror", "inflate", "pivot", "rotation", "origin",
                "size", "uv"}
            _assert_has_accepted_keys_only(
                'cube', set(cube.keys()), acceptable_keys, cube_path)
            if 'origin' in cube:
                _assert_is_vector(
                    'origin', cube['origin'], 3, (int, float),
                    cube_path + ['origin'])
                result['origin'] = cube['origin']
            if 'size' in cube:
                _assert_is_vector(
                    'size', cube['size'], 3, (int, float),
                    cube_path + ['size'])
                result['size'] = cube['size']
            if 'rotation' in cube:
                _assert_is_vector(
                    'rotation', cube['rotation'], 3, (int, float),
                    cube_path + ['rotation'])
                result['rotation'] = cube['rotation']
            if 'pivot' in cube:
                _assert_is_vector(
                    'pivot', cube['pivot'], 3, (int, float),
                    cube_path + ['pivot'])
                result['pivot'] = cube['pivot']
            if 'inflate' in cube:
                _assert_is_type(
                    'inflate', cube['inflate'], (int, float), cube_path + ['inflate'])
                result['inflate'] = cube['inflate']
            if 'mirror' in cube:
                _assert_is_type(
                    'mirror', cube['mirror'], (bool,), cube_path + ['mirror'])
                result['mirror'] = cube['mirror']
            if 'uv' in cube:
                _assert_is_type(
                    'uv', cube['uv'], (list, dict), cube_path + ['uv'])
                if isinstance(cube['uv'], dict):
                    raise ImportingNotImplementedError(
                        'uv dictionary', cube_path + ['uv'])
                elif isinstance(cube['uv'], list):
                    _assert_is_vector(
                        'uv', cube['uv'], 2, (int, float), cube_path + ['uv'])
                    result['uv'] = cube['uv']
                else:
                    raise FileIsNotAModelException(
                        f'{cube_path + ["uv"]}::{"uv"} is not an '
                        f'instance of {(list, dict)}')
            return result
        elif parser_version == '1.8.0':
            _assert_is_type('cube', cube, (dict,), cube_path)
            # There is no required keys {} is a valid cube
            acceptable_keys = {"origin", "size", "uv", "inflate", "mirror"}
            _assert_has_accepted_keys_only(
                'cube', set(cube.keys()), acceptable_keys, cube_path)
            if 'origin' in cube:
                _assert_is_vector(
                    'origin', cube['origin'], 3, (int, float),
                    cube_path + ['origin'])
                result['origin'] = cube['origin']
            if 'size' in cube:
                _assert_is_vector(
                    'size', cube['size'], 3, (int, float),
                    cube_path + ['size'])
                result['size'] = cube['size']
            if 'inflate' in cube:
                _assert_is_type(
                    'inflate', cube['inflate'], (int, float), cube_path + ['inflate'])
                result['inflate'] = cube['inflate']
            if 'mirror' in cube:
                _assert_is_type(
                    'mirror', cube['mirror'], (bool,), cube_path + ['mirror'])
                result['mirror'] = cube['mirror']
            if 'uv' in cube:
                _assert_is_type(
                    'uv', cube['uv'], (list,), cube_path + ['uv'])
                _assert_is_vector(
                    'uv', cube['uv'], 2, (int, float), cube_path + ['uv'])
                result['uv'] = cube['uv']
            return result
        else:
            raise FileIsNotAModelException('Unsuported format version')

    def _load_locators(
            self, locators: Any, locators_path: List) -> Dict[str, Any]:
        '''
        Returns the locators from the list of locators with added missing
        values.

        - `locators: Any` - list of locators
        - `locators_path: List[Any]` - path to the locators list (for error
          messages)
        '''
        result = {}
        parser_version = pick_version_parser(
            ('1.12.0', '1.8.0'), self.format_version)
        if parser_version == '1.12.0' or parser_version == '1.8.0':
            _assert_is_type(
                'locators property', locators, (dict,), locators_path)
            for i, locator in locators.items():
                locator_path = locators_path + [i]
                result[i] = self._load_locator(locator, locator_path)
            return result
        else:
            raise FileIsNotAModelException('Unsuported format version')

    def _load_locator(self, locator: Any, locator_path: List) -> Any:
        '''
        Returns the locators from the list of locators with added missing
        values.

        - `locator: Any` - the locator
        - `locator_path: List[Any]` - path to the locator
        '''
        parser_version = pick_version_parser(
            ('1.12.0', '1.8.0'), self.format_version)
        if parser_version == '1.12.0':
            if isinstance(locator, list):
                _assert_is_vector('locator', locator, 3, (int, float), locator_path)
                return locator
            elif isinstance(locator, dict):
                raise ImportingNotImplementedError('locator', locator_path)
            raise FileIsNotAModelException(
                f'{locator_path + ["locator"]}::{"locator"} is not an '
                f'instance of {(list, dict)}')
        elif parser_version == '1.8.0':
            _assert_is_type('locator', locator, (list,), locator_path)
            _assert_is_vector('locator', locator, 3, (int, float), locator_path)
            return locator
        else:
            raise FileIsNotAModelException('Unsuported format version')

class ImportLocator:
    '''Represents Minecraft locator during import operation.'''
    def __init__(self, name: str, position: Tuple[float, float, float]):
        self.name = name
        self.position = position

        self.blend_empty: Optional[bpy_types.Object] = None


class ImportCube:
    '''Represents minecraft cube during import operation.'''
    def __init__(
            self, data: Dict):
        '''
        Creates ImportCube object created from a dictinary (part of the JSON)
        file in the model.

        # Arguments:
        - `data: Dict` - the part of the Minecraft model JSON file that represents
        the cube.
        '''
        self.blend_cube: Optional[bpy_types.Object] = None

        self.uv: Tuple[int, int] = tuple(# type: ignore
            data['uv'])
        self.mirror: bool = data['mirror']
        self.origin: Tuple[float, float, float] = tuple(  # type: ignore
            data['origin'])
        self.pivot: Tuple[float, float, float] = tuple(  # type: ignore
            data['pivot'])
        self.size: Tuple[float, float, float] = tuple(  # type: ignore
            data['size'])
        self.rotation: Tuple[float, float, float] = tuple(  # type: ignore
            data['rotation'])


class ImportBone:
    '''Represents minecraft bone during import operation.'''
    def __init__(self, data: Dict):
        '''
        Creates ImportBone object created from a dictinary (part of the JSON)
        file in the model.

        # Arguments:
        - `data: Dict` - the part of the Minecraft model JSON file that represents
        the bone.
        '''
        self.blend_empty: Optional[bpy_types.Object] = None

        # Locators
        locators: List[ImportLocator] = []
        for k, v in data['locators'].items():
            locators.append(ImportLocator(k, tuple(v)))  # type: ignore
        # Cubes
        import_cubes: List[ImportCube] = []
        for cube in data['cubes']:
            import_cubes.append(ImportCube(cube))

        self.name: str = data['name']
        self.parent = data['parent']
        self.cubes = import_cubes
        self.locators = locators
        self.pivot: Tuple[float, float, float] = tuple(  # type: ignore
            data['pivot'])
        self.rotation: Tuple[float, float, float] = tuple(  # type: ignore
            data['rotation'])
        self.mirror = data['mirror']


class ImportGeometry:
    '''Represents whole minecraft geometry during import operation.'''
    def __init__(self, loader: ModelLoader):
        # TODO - update description
        '''
        Creates ImportGeometry object.

        - `loader: ModelLoader` - a loader object with all of the required
          model properties.
        '''
        # Set the values
        self.identifier = loader.description['identifier']
        self.texture_width = int(loader.description['texture_width'])
        self.texture_height = int(loader.description['texture_height'])
        self.bones: Dict[str, ImportBone] = {}
        self.uv_converter = CoordinatesConverter(
            np.array([[0, self.texture_width], [0, self.texture_height]]),
            np.array([[0, 1], [1, 0]])
        )

        # Read bones
        for bone in loader.bones:
            import_bone = ImportBone(bone)
            self.bones[import_bone.name] = import_bone


    def build(self, context: bpy_types.Context):
        '''
        Builds the geometry in Blender based on ImportGeometry object.

        # Arguments:
        `context: bpy_types.Context` - the context of running the operator.
        '''
        # context.view_layer.update()
        # Create objects - and set their pivots
        for bone in self.bones.values():
            # 1. Spawn bone (empty)
            bpy.ops.object.empty_add(type='SPHERE', location=(0, 0, 0))
            bone_obj: bpy_types.Object
            bone_obj = bone.blend_empty = context.object
            _mc_pivot(bone_obj, bone.pivot)  # 2. Apply translation
            bone_obj.name = bone.name  # 3. Apply custom properties
            bone_obj['mc_is_bone'] = {}
            for cube in bone.cubes:
                cube_obj: bpy_types.Object
                # 1. Spawn cube
                bpy.ops.mesh.primitive_cube_add(
                    size=1, enter_editmode=False, location=(0, 0, 0)
                )
                cube_obj = cube.blend_cube = context.object

                # 2. Set uv
                # warning! Moving this code below cube transformation would
                # break it because bound_box is not getting updated properly
                # before the end of running of the opperator.
                if cube.mirror:
                    cube_obj['mc_mirror'] = {}
                _set_uv(
                    self.uv_converter,
                    CubePolygons.build(cube_obj, cube.mirror), cube.mirror,
                    cube.size, cube.uv, cube_obj.data.uv_layers.active)

                _mc_set_size(cube_obj, cube.size)  # 3. Set size
                _mc_pivot(cube_obj, cube.pivot)  # 4. Move pivot
                # 5. Apply translation
                _mc_translate(cube_obj, cube.origin, cube.size, cube.pivot)

            for locator in bone.locators:
                # 1. Spawn locator (empty)
                locator_obj: bpy_types.Object
                bpy.ops.object.empty_add(type='SPHERE', location=(0, 0, 0))
                locator_obj = locator.blend_empty = context.object
                _mc_pivot(locator_obj, locator.position)  # 2. Apply translation
                # 3. Apply custom properties
                locator_obj.name = locator.name

        # Parent objects (keep offset)
        for bone in self.bones.values():
            bone_obj = bone.blend_empty
            # 1. Parent bone keep transform
            if bone.parent is not None and bone.parent in self.bones:
                parent_obj: bpy_types.Object = self.bones[
                    bone.parent
                ].blend_empty
                context.view_layer.update()
                bone_obj.parent = parent_obj
                bone_obj.matrix_parent_inverse = (
                    parent_obj.matrix_world.inverted()
                )
            # 2. Parent cubes keep transform
            for cube in bone.cubes:
                cube_obj = cube.blend_cube
                context.view_layer.update()
                cube_obj.parent = bone_obj
                cube_obj.matrix_parent_inverse = (
                    bone_obj.matrix_world.inverted()
                )
            # 3. Parent locators keep transform
            for locator in bone.locators:
                locator_obj = locator.blend_empty
                context.view_layer.update()
                locator_obj.parent = bone_obj
                locator_obj.matrix_parent_inverse = (
                    bone_obj.matrix_world.inverted()
                )

        # Rotate objects
        for bone in self.bones.values():
            bone_obj = bone.blend_empty
            context.view_layer.update()
            _mc_rotate(bone_obj, bone.rotation)
            for cube in bone.cubes:
                cube_obj = cube.blend_cube
                _mc_rotate(cube_obj, cube.rotation)


def _mc_translate(
        obj: bpy_types.Object, mctranslation: Tuple[float, float, float],
        mcsize: Tuple[float, float, float],
        mcpivot: Tuple[float, float, float]
    ):
    '''
    Translates a blender object using a translation vector written in Minecraft
    coordinates system.

    # Arguments:
    - `obj: bpy_types.Object` - blender object to transform..
    - `mctranslation: Tuple[float, float, float]` - minecraft translation.
    - `mcsize: Tuple[float, float, float]` - minecraft size.
    - `mcpivot: Tuple[float, float, float]` - minecraft pivot.
    '''
    pivot_offset = mathutils.Vector(
        np.array(mcpivot)[[0, 2, 1]] / MINECRAFT_SCALE_FACTOR
    )
    size_offset = mathutils.Vector(
        (np.array(mcsize)[[0, 2, 1]] / 2) / MINECRAFT_SCALE_FACTOR
    )
    translation = mathutils.Vector(
        np.array(mctranslation)[[0, 2, 1]] / MINECRAFT_SCALE_FACTOR
    )
    for vertex in obj.data.vertices:
        vertex.co += (translation - pivot_offset + size_offset)


def _mc_set_size(obj: bpy_types.Object, mcsize: Tuple[float, float, float]):
    '''
    Scales a blender object using scale vector written in minecraft coordinates
    system.

    # Arguments:
    - `obj: bpy_types.Object` - Blender object
    - `mcsize: Tuple[float, float, float]` - Minecraft object size.
    '''
    pos_delta = (
        (np.array(mcsize)[[0, 2, 1]] / 2) / MINECRAFT_SCALE_FACTOR
    )
    data = obj.data
    # 0. ---; 1. --+; 2. -+-; 3. -++; 4. +--; 5. +-+; 6. ++- 7. +++
    data.vertices[0].co = mathutils.Vector(pos_delta * np.array([-1, -1, -1]))
    data.vertices[1].co = mathutils.Vector(pos_delta * np.array([-1, -1, 1]))
    data.vertices[2].co = mathutils.Vector(pos_delta * np.array([-1, 1, -1]))
    data.vertices[3].co = mathutils.Vector(pos_delta * np.array([-1, 1, 1]))
    data.vertices[4].co = mathutils.Vector(pos_delta * np.array([1, -1, -1]))
    data.vertices[5].co = mathutils.Vector(pos_delta * np.array([1, -1, 1]))
    data.vertices[6].co = mathutils.Vector(pos_delta * np.array([1, 1, -1]))
    data.vertices[7].co = mathutils.Vector(pos_delta * np.array([1, 1, 1]))


def _mc_pivot(obj: bpy_types.Object, mcpivot: Tuple[float, float, float]):
    '''
    Moves a pivot of an blender object using coordinates written in minecraft
    coordinates system.

    # Arguments:
    - `obj: bpy_types.Object` - Blender object
    - `mcpivot: Tuple[float, float, float]` - Minecraft object pivot point.
    '''
    translation = mathutils.Vector(
        np.array(mcpivot)[[0, 2, 1]] / MINECRAFT_SCALE_FACTOR
    )
    obj.location += translation


def _mc_rotate(
        obj: bpy_types.Object, mcrotation: Tuple[float, float, float]
    ):
    '''
    Rotates a blender object using minecraft coordinates system for rotation
    vector.

    # Arguments:
    - `obj: bpy_types.Object` - Blender object
    - `mcrotation: Tuple[float, float, float]` - Minecraft object rotation.
    '''
    rotation = mathutils.Euler(
        (np.array(mcrotation)[[0, 2, 1]] * np.array([1, 1, -1])) * math.pi/180,
        'XZY'
    )
    obj.rotation_euler.rotate(rotation)

def _set_uv(
        uv_converter: CoordinatesConverter, cube_polygons: CubePolygons,
        mirror: bool, size: Tuple[float, float, float], uv: Tuple[float, float],
        uv_layer: bpy.types.MeshUVLoopLayer):
    '''
    Sets the uv of a face of a blender cube mesh based on some minecraft
    properties.

    - `uv_converter: CoordinatesConverter` - converter used for converting from
      minecraft uv coordinates to blender uv coordinates
    - `cube_polygons: CubePolygons` - CybePolygons object created from the mesh
    - `mirror: bool` - cube mirror property
    - `size: Tuple[float, float, float]` - cube size
    - `uv: Tuple[float, float]` - uv coordinate of the cube
    - `uv_layer: bpy.types.MeshUVLoopLayer` - uv layer of the mesh
    '''
    width, height, depth = size
    if mirror:
        cp1, cp3 = cube_polygons.west, cube_polygons.east
    else:
        cp1, cp3 = cube_polygons.east, cube_polygons.west

    uv_data = uv_layer.data
    def set_uv(cp: CubePolygon, size: Tuple[float, float], uv_local: Tuple[float, float]):
        cp_loop_indices = cp.side.loop_indices
        cp_order = cp.order

        left_down = cp_loop_indices[cp_order[0]]
        right_down = cp_loop_indices[cp_order[1]]
        right_up = cp_loop_indices[cp_order[2]]
        left_up = cp_loop_indices[cp_order[3]]

        uv_data[left_down].uv = uv_converter.convert((
            uv[0] + uv_local[0],
            uv[1] + uv_local[1] + size[1]))
        uv_data[right_down].uv = uv_converter.convert((
            uv[0] + uv_local[0] + size[0],
            uv[1] + uv_local[1] + size[1]))
        uv_data[right_up].uv = uv_converter.convert((
            uv[0] + uv_local[0] + size[0],
            uv[1] + uv_local[1]))
        uv_data[left_up].uv = uv_converter.convert((
            uv[0] + uv_local[0],
            uv[1] + uv_local[1]))

    # right/left
    set_uv(cp1, (depth, height), (0, depth))
    # front
    set_uv(cube_polygons.north, (width, height), (depth, depth))
    # left/right
    set_uv(cp3, (depth, height), (depth + width, depth))
    # back
    set_uv(cube_polygons.south, (width, height), (2*depth + width, depth))
    # top
    set_uv(cube_polygons.up, (width, depth), (depth, 0))
    # bottom
    set_uv(cube_polygons.down, (width, depth), (depth + width, 0))