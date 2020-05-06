'''
Functions and objects shared between other modules of Mcblend.
'''
from __future__ import annotations

import math
from enum import Enum
import typing as tp

import numpy as np

import bpy_types
import mathutils


MINECRAFT_SCALE_FACTOR = 16


class MCObjType(Enum):
    '''
    Used to mark what type of Minecraft object should be created from an object
    in blender.
    '''
    CUBE = 'CUBE'
    BONE = 'BONE'
    BOTH = 'BOTH'
    LOCATOR = 'LOCATOR'


class ObjectId(tp.NamedTuple):
    '''
    Unique ID of a mesh, empty or a bone. For meshes and empties it's bone_name
    is just an empty string and the name is the name of the object. For bones
    the ID uses both the name (armature name) and bone name.
    '''
    name: str
    bone_name: str


class ObjectMcProperties:
    '''
    A class that wraps around Blender objects (meshes, empties and bones) and
    gives access to some data necesary to export the model into Minecraft
    format.
    '''
    def __init__(
            self, thisobj_id: ObjectId, thisobj: bpy_types.Object,
            mcparent: tp.Optional[ObjectId], mcchildren: tp.List[ObjectId],
            mctype: MCObjType):
        self.thisobj_id = thisobj_id
        self.thisobj: bpy_types.Object = thisobj
        self.mcparent: tp.Optional[ObjectId] = mcparent
        self.mcchildren: tp.List[ObjectId] = mcchildren
        self.mctype: MCObjType = mctype

    def clear_uv_layers(self):
        '''
        Clears the uv layers from the object. Rises exception when the object
        is armature
        '''
        if self.thisobj.type == 'ARMATURE':
            raise Exception('Invalid method for ARMATURE.')
        while len(self.thisobj.data.uv_layers) > 0:
            self.thisobj.data.uv_layers.remove(
                self.thisobj.data.uv_layers[0]
            )

    def set_mc_uv(self, uv: tp.Tuple[int, int]):
        '''Sets the mc_uv property of the cube.'''
        self.thisobj['mc_uv'] = uv

    def get_mc_uv(self) -> tp.Tuple[int, int]:
        '''Returns the mc_uv property of the object.'''
        return tuple(self.thisobj['mc_uv'])  # type: ignore

    def has_uv(self):
        '''Returns true if the object has mc_uv property.'''
        return 'mc_uv' in self.thisobj

    def has_mc_inflate(self) -> bool:
        '''Returns true if the object has the mc_inflate property'''
        return 'mc_inflate' in self.thisobj

    def get_mc_inflate(self) -> float:
        '''Returns the value of mc_inflate property of the object'''
        return self.thisobj['mc_inflate']

    def has_mc_mirror(self) -> bool:
        '''Returns true if the object has mc_mirror object'''
        return 'mc_mirror' in self.thisobj

    def has_mc_is_bone(self) -> bool:
        '''Returns true if the object has mc_is_bone property'''
        return 'mc_is_bone' in self.thisobj

    def has_mc_uv_group(self) -> bool:
        '''Return True if the object has mc_uv_group property'''
        return 'mc_uv_group' in self.thisobj

    def get_mc_uv_group(self) -> str:
        '''Returns the value of mc_uv_group property of the object'''
        return self.thisobj['mc_uv_group']

    def data_polygons(self) -> tp.Any:
        '''Returns the polygons (faces) of the object'''
        return self.thisobj.data.polygons

    def data_vertices(self) -> tp.Any:
        '''Returns the vertices of the object'''
        return self.thisobj.data.vertices

    def data_uv_layers_active_data(self) -> tp.Any:
        '''Return the data of active uv-layers of the object'''
        return self.thisobj.data.uv_layers.active.data

    def data_uv_layers_new(self):
        '''Adds UV-layer to an object.'''
        self.thisobj.data.uv_layers.new()

    def name(self) -> str:
        '''Returns the name of the object'''
        if self.thisobj.type == 'ARMATURE':
            return self.thisobj.pose.bones[
                self.thisobj_id.bone_name
            ].name
        return self.thisobj.name.split('.')[0]

    def type(self) -> str:
        '''Returns the type of the object (ARMATURE, MESH or EMPTY).'''
        return self.thisobj.type

    def bound_box(self) -> tp.Any:
        '''Returns the bound box of the object'''
        return self.thisobj.bound_box

    def matrix_world(self) -> mathutils.Matrix:
        '''Return the translation matrix (matrix_world) of the object.'''
        if self.thisobj.type == 'ARMATURE':
            return self.thisobj.matrix_world.copy() @ self.thisobj.pose.bones[
                self.thisobj_id.bone_name
            ].matrix.copy()
        return self.thisobj.matrix_world.copy()


class ObjectMcTransformations(tp.NamedTuple):
    '''
    Temporary properties of transformations of an object (mesh or empty)
    for the minecraft animation. Changes in these values over the frames of the
    animation are used to calculate the values for minecraft animation json.
    '''
    location: np.array
    scale: np.array
    rotation: np.array

def get_vect_json(arr: tp.Iterable) -> tp.List[float]:
    '''
    Changes the iterable whith numbers into basic python list of floats.
    Values from the original iterable are rounded to the 3rd deimal
    digit. If value is integer than its type is changed to int to skip
    unnecesary zero decimal.

    # Arguments:
    - `arr: tp.Iterable` - an iterable with numbers.
    '''
    result = [round(i, 3) for i in arr]
    for i, _ in enumerate(result):
        if result[i] == -0.0:
            result[i] = 0.0
        if float(result[i]).is_integer():
            result[i] = int(result[i])
    return result


def get_local_matrix(
        parent_world_matrix: mathutils.Matrix,
        child_world_matrix: mathutils.Matrix) -> mathutils.Matrix:
    '''
    Returns translation matrix of child in relation to parent.
    In space defined by parent translation matrix.

    # Arguments:
    - `parent_world_matrix: mathutils.Matrix` - matrix_world of parent object.
    - `child_world_matrix: mathutils.Matrix` - matrix_world of child object.
    # Returns:
    `mathutils.Matrix` - translation matrix for child object in parent space.
    '''
    return (
        parent_world_matrix.inverted() @ child_world_matrix
    )


def get_mcrotation(
        child_matrix: mathutils.Matrix,
        parent_matrix: tp.Optional[mathutils.Matrix] = None) -> np.ndarray:
    '''
    Returns the rotation of mcbone.

    # Arguments:
    - `child_matrix: mathutils.Matrix` - the matrix_world of the object that
      represents Minecraft bone.
    - `parent_matrix: Optional[mathutils.Matrix]` - the matrix_world of the
      parent bone object (optional).

    # Returns:
    `np.ndarray` - numpy array with the rotation in Minecraft format.
    '''
    def local_rotation(
            child_matrix: mathutils.Matrix, parent_matrix: mathutils.Matrix
        ) -> mathutils.Euler:
        '''
        Reuturns Euler rotation of a child matrix in relation to parent matrix
        '''
        child_matrix = child_matrix.normalized()
        parent_matrix = parent_matrix.normalized()
        return (
            parent_matrix.inverted() @ child_matrix
        ).to_quaternion().to_euler('XZY')

    if parent_matrix is not None:
        result = local_rotation(
            child_matrix, parent_matrix
        )
    else:
        result = child_matrix.to_euler('XZY')
    result = np.array(result)[[0, 2, 1]]
    result = result * np.array([1, -1, 1])
    result = result * 180/math.pi  # math.degrees() for array
    return result


def get_mcube_size(objprop: ObjectMcProperties) -> np.ndarray:
    '''
    Returns cube size based on the bounding box of an object.

    # Arguments:
    - `objprop: ObjectMcProperties` - the properties of the object

    # Returns:
    `np.ndarray` - the size of the object in Minecraft format.
    '''
    # 0. ---; 1. --+; 2. -++; 3. -+-; 4. +--; 5. +-+; 6. +++; 7. ++-
    bound_box = objprop.bound_box()
    return (np.array(bound_box[6]) - np.array(bound_box[0]))[[0, 2, 1]]


def get_mccube_position(objprop: ObjectMcProperties) -> np.ndarray:
    '''
    Returns cube position based on the bounding box of an object.

    # Arguments:
    - `objprop: ObjectMcProperties` - the properties of the object

    # Returns:
    `np.ndarray` - the position of the object in Minecraft format.
    '''
    return np.array(objprop.bound_box()[0])[[0, 2, 1]]


def get_mcpivot(
        objprop: ObjectMcProperties,
        object_properties: tp.Dict[ObjectId, ObjectMcProperties]
    ) -> np.ndarray:
    '''
    Returns the pivot point of Minecraft object.

    # Arguments:
    - `objprop: ObjectMcProperties` - the properties of Minecraft object.
    - `object_properties: Dict[ObjectId, ObjectMcProperties]` - the
      other objects.

    # Returns:
    `np.ndarray` - the pivot point of Minecraft object.
    '''
    def local_crds(
            parent_matrix: mathutils.Matrix, child_matrix: mathutils.Matrix
        ) -> mathutils.Vector:
        '''Local coordinates of child matrix inside parent matrix'''
        parent_matrix = parent_matrix.normalized()  # eliminate scale
        child_matrix = child_matrix.normalized()  # eliminate scale
        return get_local_matrix(parent_matrix, child_matrix).to_translation()

    def _get_mcpivot(objprop: ObjectMcProperties) -> mathutils.Vector:
        if objprop.mcparent is not None:
            result = local_crds(
                object_properties[objprop.mcparent].matrix_world(),
                objprop.matrix_world()
            )
            result += _get_mcpivot(object_properties[objprop.mcparent])
        else:
            result = objprop.matrix_world().to_translation()
        return result

    return np.array(_get_mcpivot(objprop).xzy)


def loop_objects(objects: tp.List) -> tp.Iterable[tp.Tuple[ObjectId, tp.Any]]:
    '''
    Loops over the empties, meshes and armature objects and yields them and
    their ids. If object is an armatre than it loops over every bone and
    yields the armature and the id of the bone.

    # Arguments:
    - `objects: List` - the list of blender objects

    # Returns:
    `Iterable[tp.Tuple[ObjectId, Any]]` - iterable that goes throug objects and
    bones.
    '''
    for obj in objects:
        if obj.type in ['MESH', 'EMPTY']:
            yield ObjectId(obj.name, ''), obj
        elif obj.type == 'ARMATURE':
            for bone in obj.data.bones:
                yield ObjectId(obj.name, bone.name), obj

def get_parent_mc_bone(obj: bpy_types.Object) -> tp.Optional[ObjectId]:
    '''
    Goes up through the ancesstors of an bpy_types.Object and tries to find
    the object that represents its parent bone in Minecraft model.

    # Arguments:
    - `obj: bpy_types.Object` - a Blender object which will be truned into
    Minecraft bone

    # Returns:
    `tp.Optional[ObjectId]` - parent Minecraft bone of the object or None.
    '''
    obj_id = None
    while obj.parent is not None:
        if obj.parent_type == 'BONE':
            return ObjectId(obj.parent.name, obj.parent_bone)

        if obj.parent_type == 'OBJECT':
            obj = obj.parent
            obj_id = ObjectId(obj.name, '')
            if obj.type == 'EMPTY' or 'mc_is_bone' in obj:
                return obj_id
        else:
            raise Exception(f'Unsuported parent type {obj.parent_type}')
    return obj_id


def get_name_conflicts(
        object_properties: tp.Dict[ObjectId, ObjectMcProperties]
    ) -> str:
    '''
    Looks through the object_properties dictionary and tries to find name
    conflicts. Returns empty string (when there are no conflicts) or a name
    of an object that causes the conflict.

    # Arguments:
    - `object_properties: Dict[ObjectId, ObjectMcProperties]` - the properties
    of all objects.

    # Returns:
    `str` - name of conflictiong objects or empty string.
    '''
    names: tp.List[str] = []
    for objprop in object_properties.values():
        if objprop.mctype not in [MCObjType.BONE, MCObjType.BOTH]:
            continue  # Only bone names conflicts count
        if objprop.name() in names:
            return objprop.name()
        names.append(objprop.name())
    return ''


def get_object_mcproperties(
        context: bpy_types.Context
        ) -> tp.Dict[ObjectId, ObjectMcProperties]:
    '''
    Loops through context.selected_objects and returns a dictionary with custom
    properties of mcobjects. Returned dictionary uses the ObjectId of the
    objects as keys and the custom properties as values.

    # Arguments:
    - `context: bpy_types.Context` - the context of running the operator.

    # Returns:
    `Dict[ObjectId, ObjectMcProperties]` - the properties of all objects.
    '''
    # pylint: disable=R0912
    properties: tp.Dict[ObjectId, ObjectMcProperties] = {}
    for obj_id, obj in loop_objects(context.selected_objects):
        curr_obj_mc_type: MCObjType
        curr_obj_mc_parent: tp.Optional[ObjectId] = None
        if obj.type == 'EMPTY':
            curr_obj_mc_type = MCObjType.BONE
            if (obj.parent is not None and len(obj.children) == 0 and
                    'mc_is_bone' not in obj):
                curr_obj_mc_type = MCObjType.LOCATOR

            if obj.parent is not None:
                curr_obj_mc_parent = get_parent_mc_bone(obj)
        elif obj.type == 'MESH':
            if obj.parent is None or 'mc_is_bone' in obj:
                curr_obj_mc_type = MCObjType.BOTH
            else:
                curr_obj_mc_parent = get_parent_mc_bone(obj)
                curr_obj_mc_type = MCObjType.CUBE
        elif obj.type == 'ARMATURE':
            bone = obj.data.bones[obj_id.bone_name]
            if bone.parent is None and len(bone.children) == 0:
                continue  # Skip empty bones
            curr_obj_mc_type = MCObjType.BONE
            if bone.parent is not None:
                curr_obj_mc_parent = ObjectId(obj.name, bone.parent.name)
        else:  # Handle only empty, meshes and armatures
            continue
        properties[obj_id] = ObjectMcProperties(
            obj_id, obj, curr_obj_mc_parent,
            [], curr_obj_mc_type
        )
    # Fill the children property. Must be in separate loop to reverse the
    # effect of get_parent_mc_bone() function.
    for objid, objprop in properties.items():
        if objprop.mcparent is not None and objprop.mcparent in properties:
            properties[objprop.mcparent].mcchildren.append(objid)

    return properties


def pick_closest_rotation(
        modify: np.ndarray, close_to: np.ndarray,
        original_rotation: tp.Optional[np.ndarray] = None
    ) -> np.ndarray:
    '''
    Takes two numpy.arrays that represent euler rotation in (using degrees).
    Modifies the values of 'modify' vector to get different representations
    of the same rotation. Picks the vector which is the
    closest to 'close_to' vector (using euclidean distance).

    *Original_rotation is added specificly to fix some issues with bones
    which were rotated before the animation. Issue #25 on Github describes
    the problem in detail.

    # Arguments:
    - `modify: np.ndarray` - a vector that represents rotation. The function
      looks for equivalents of this rotation.
    - `close_to: np.ndarray` - a vector that represents other rotation. The
      function tries to pick rotation as close as possible to this one.
    - `original_rotation: tp.Optional[np.ndarray]` - the original rotation of
      the object (befor any animation starts).

    # Returns:
    `np.ndarray` - rotation vector (a different representation of the modify
    vector)
    '''
    if original_rotation is None:
        original_rotation = np.array([0.0, 0.0, 0.0])

    def _pick_closet_location(
            modify: np.ndarray, close_to: np.ndarray
        ) -> tp.Tuple[float, np.ndarray]:
        choice = modify
        distance = np.linalg.norm(choice - close_to)

        for i in range(3):  # Adds removes 360 to all 3 axis (picks the best)
            arr = np.zeros(3)
            arr[i] = 360
            while choice[i] < close_to[i]:
                new_choice = choice + arr
                new_distance = np.linalg.norm(new_choice - close_to)
                if new_distance > distance:
                    break
                distance, choice = new_distance, new_choice
            while choice[i] > close_to[i]:
                new_choice = choice - arr
                new_distance = np.linalg.norm(new_choice - close_to)
                if new_distance > distance:
                    break
                distance, choice = new_distance, new_choice
        return distance, choice

    distance1, choice1 = _pick_closet_location(modify, close_to)
    distance2, choice2 = _pick_closet_location(  # Counterintuitive but works
        # pylint: disable=C0330
        (
            modify +
            np.array([180, 180 + original_rotation[1] * 2, 180])) *
            np.array([1, -1, 1]
        ),
        close_to
    )
    if distance2 < distance1:
        return choice2
    return choice1
