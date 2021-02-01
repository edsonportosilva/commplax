import functools
import jax.numpy as jnp
from typing import Any, Callable, NamedTuple, Tuple, Union
from jax.util import partial
from jax.experimental.optimizers import Optimizer, Schedule, optimizer

# "patched" optimizers to support grad on f: C -> R
# https://jax.readthedocs.io/en/latest/notebooks/autodiff_cookbook.html#Complex-numbers-and-differentiation

@optimizer
def sgd(step_size):
  """Construct optimizer triple for stochastic gradient descent.

  Args:
    step_size: positive scalar, or a callable representing a step size schedule
      that maps the iteration index to positive scalar.

  Returns:
    An (init_fun, update_fun, get_params) triple.
  """
  step_size = make_schedule(step_size)
  def init(x0):
    return x0
  def update(i, g, x):
    return x - step_size(i) * jnp.conj(g)
  def get_params(x):
    return x
  return Optimizer(init, update, get_params)


@optimizer
def momentum(step_size: Schedule, mass: float):
  """Construct optimizer triple for SGD with momentum.

  Args:
    step_size: positive scalar, or a callable representing a step size schedule
      that maps the iteration index to positive scalar.
    mass: positive scalar representing the momentum coefficient.

  Returns:
    An (init_fun, update_fun, get_params) triple.
  """
  step_size = make_schedule(step_size)
  def init(x0):
    v0 = jnp.zeros_like(x0)
    return x0, v0
  def update(i, g, state):
    x, velocity = state
    velocity = mass * velocity + jnp.conj(g)
    x = x - step_size(i) * velocity
    return x, velocity
  def get_params(state):
    x, _ = state
    return x
  return init, update, get_params


@optimizer
def nesterov(step_size: Schedule, mass: float):
  """Construct optimizer triple for SGD with Nesterov momentum.

  Args:
    step_size: positive scalar, or a callable representing a step size schedule
      that maps the iteration index to positive scalar.
    mass: positive scalar representing the momentum coefficient.

  Returns:
    An (init_fun, update_fun, get_params) triple.
  """
  step_size = make_schedule(step_size)
  def init(x0):
    v0 = jnp.zeros_like(x0)
    return x0, v0
  def update(i, g, state):
    x, velocity = state
    velocity = mass * velocity + g
    x = x - step_size(i) * (mass * velocity + g)
    return x, velocity
  def get_params(state):
    x, _ = state
    return x
  return init, update, get_params


@optimizer
def adagrad(step_size, momentum=0.9):
  """Construct optimizer triple for Adagrad.

  Adaptive Subgradient Methods for Online Learning and Stochastic Optimization:
  http://www.jmlr.org/papers/volume12/duchi11a/duchi11a.pdf

  Args:
    step_size: positive scalar, or a callable representing a step size schedule
      that maps the iteration index to positive scalar.
    momentum: optional, a positive scalar value for momentum

  Returns:
    An (init_fun, update_fun, get_params) triple.
  """
  step_size = make_schedule(step_size)

  def init(x0):
    g_sq = jnp.zeros_like(x0)
    m = jnp.zeros_like(x0)
    return x0, g_sq, m

  def update(i, g, state):
    x, g_sq, m = state
    g_sq += jnp.square(g)
    g_sq_inv_sqrt = jnp.where(g_sq > 0, 1. / jnp.sqrt(g_sq), 0.0)
    m = (1. - momentum) * (g * g_sq_inv_sqrt) + momentum * m
    x = x - step_size(i) * m
    return x, g_sq, m

  def get_params(state):
    x, _, _ = state
    return x

  return init, update, get_params


@optimizer
def rmsprop(step_size, gamma=0.9, eps=1e-8):
  """Construct optimizer triple for RMSProp.

  Args:
    step_size: positive scalar, or a callable representing a step size schedule
      that maps the iteration index to positive scalar.
      gamma: Decay parameter.
      eps: Epsilon parameter.

  Returns:
    An (init_fun, update_fun, get_params) triple.
  """
  step_size = make_schedule(step_size)
  def init(x0):
    avg_sq_grad = jnp.zeros_like(x0)
    return x0, avg_sq_grad
  def update(i, g, state):
    x, avg_sq_grad = state
    avg_sq_grad = avg_sq_grad * gamma + jnp.square(g) * (1. - gamma)
    x = x - step_size(i) * g / jnp.sqrt(avg_sq_grad + eps)
    return x, avg_sq_grad
  def get_params(state):
    x, _ = state
    return x
  return init, update, get_params


@optimizer
def rmsprop_momentum(step_size, gamma=0.9, eps=1e-8, momentum=0.9):
  """Construct optimizer triple for RMSProp with momentum.

  This optimizer is separate from the rmsprop optimizer because it needs to
  keep track of additional parameters.

  Args:
    step_size: positive scalar, or a callable representing a step size schedule
      that maps the iteration index to positive scalar.
    gamma: Decay parameter.
    eps: Epsilon parameter.
    momentum: Momentum parameter.

  Returns:
    An (init_fun, update_fun, get_params) triple.
  """
  step_size = make_schedule(step_size)
  def init(x0):
    avg_sq_grad = jnp.zeros_like(x0)
    mom = jnp.zeros_like(x0)
    return x0, avg_sq_grad, mom
  def update(i, g, state):
    x, avg_sq_grad, mom = state
    avg_sq_grad = avg_sq_grad * gamma + jnp.square(g) * (1. - gamma)
    mom = momentum * mom + step_size(i) * g / jnp.sqrt(avg_sq_grad + eps)
    x = x - mom
    return x, avg_sq_grad, mom
  def get_params(state):
    x, _, _ = state
    return x
  return init, update, get_params


@optimizer
def adam(step_size, b1=0.9, b2=0.999, eps=1e-8):
  """Construct optimizer triple for Adam.

  Args:
    step_size: positive scalar, or a callable representing a step size schedule
      that maps the iteration index to positive scalar.
    b1: optional, a positive scalar value for beta_1, the exponential decay rate
      for the first moment estimates (default 0.9).
    b2: optional, a positive scalar value for beta_2, the exponential decay rate
      for the second moment estimates (default 0.999).
    eps: optional, a positive scalar value for epsilon, a small constant for
      numerical stability (default 1e-8).

  Returns:
    An (init_fun, update_fun, get_params) triple.
  """
  step_size = make_schedule(step_size)
  def init(x0):
    m0 = jnp.zeros_like(x0)
    v0 = jnp.zeros_like(x0)
    return x0, m0, v0
  def update(i, g, state):
    x, m, v = state
    m = (1 - b1) * g.conj() + b1 * m  # First  moment estimate.
    v = (1 - b2) * (g * g.conj()) + b2 * v  # Second moment estimate.
    mhat = m / (1 - jnp.asarray(b1, m.dtype) ** (i + 1))  # Bias correction.
    vhat = v / (1 - jnp.asarray(b2, m.dtype) ** (i + 1))
    x = x - step_size(i) * mhat / (jnp.sqrt(vhat) + eps)
    return x, m, v
  def get_params(state):
    x, _, _ = state
    return x
  return init, update, get_params


@optimizer
def adamax(step_size, b1=0.9, b2=0.999, eps=1e-8):
  """Construct optimizer triple for AdaMax (a variant of Adam based on infinity norm).

  Args:
    step_size: positive scalar, or a callable representing a step size schedule
      that maps the iteration index to positive scalar.
    b1: optional, a positive scalar value for beta_1, the exponential decay rate
      for the first moment estimates (default 0.9).
    b2: optional, a positive scalar value for beta_2, the exponential decay rate
      for the second moment estimates (default 0.999).
    eps: optional, a positive scalar value for epsilon, a small constant for
      numerical stability (default 1e-8).

  Returns:
    An (init_fun, update_fun, get_params) triple.
  """
  step_size = make_schedule(step_size)
  def init(x0):
    m0 = jnp.zeros_like(x0)
    u0 = jnp.zeros_like(x0)
    return x0, m0, u0
  def update(i, g, state):
    x, m, u = state
    m = (1 - b1) * g + b1 * m  # First  moment estimate.
    u = jnp.maximum(b2 * u, jnp.abs(g))  # Update exponentially weighted infinity norm.
    x = (x - (step_size(i) / (1 - jnp.asarray(b1, m.dtype) ** (i + 1))) * m
         / (u + eps))
    return x, m, u
  def get_params(state):
    x, _, _ = state
    return x
  return init, update, get_params


@optimizer
def sm3(step_size, momentum=0.9):
  """Construct optimizer triple for SM3.

  Memory-Efficient Adaptive Optimization for Large-Scale Learning.
  https://arxiv.org/abs/1901.11150

  Args:
    step_size: positive scalar, or a callable representing a step size schedule
      that maps the iteration index to positive scalar.
    momentum: optional, a positive scalar value for momentum

  Returns:
    An (init_fun, update_fun, get_params) triple.
  """
  step_size = make_schedule(step_size)

  def splice(seq, i, x):
    lst = list(seq)
    lst[i:i+1] = x
    return lst

  def broadcast_into(ndim, x, axis):
    idx = splice([None] * ndim, axis, [slice(None)])
    return x[tuple(idx)]

  def init(x0):
    vs = [jnp.zeros(sz, dtype=x0.dtype) for sz in x0.shape]
    return x0, jnp.zeros_like(x0), vs

  def update(i, g, state):
    x, m, vs = state
    vs = [broadcast_into(g.ndim, v, i) for i, v in enumerate(vs)]
    accum = functools.reduce(jnp.minimum, vs) + jnp.square(g)
    accum_inv_sqrt = jnp.where(accum > 0, 1. / jnp.sqrt(accum), 0)
    m = (1. - momentum) * (g * accum_inv_sqrt) + momentum * m
    x = x - step_size(i) * m
    vs = [accum.max(splice(range(x.ndim), j, [])) for j in range(x.ndim)]
    return x, m, vs

  def get_params(state):
    x, _, _ = state
    return x

  return init, update, get_params


### learning rate schedules

def constant(step_size) -> Schedule:
  def schedule(i):
    return step_size
  return schedule

def exponential_decay(step_size, decay_steps, decay_rate):
  def schedule(i):
    return step_size * decay_rate ** (i / decay_steps)
  return schedule

def inverse_time_decay(step_size, decay_steps, decay_rate, staircase=False):
  if staircase:
    def schedule(i):
      return step_size / (1 + decay_rate * jnp.floor(i / decay_steps))
  else:
    def schedule(i):
      return step_size / (1 + decay_rate * i / decay_steps)
  return schedule

def polynomial_decay(step_size, decay_steps, final_step_size, power=1.0):
  def schedule(step_num):
    step_num = jnp.minimum(step_num, decay_steps)
    step_mult = (1 - step_num / decay_steps) ** power
    return step_mult * (step_size - final_step_size) + final_step_size

  return schedule

def piecewise_constant(boundaries: Any, values: Any):
  boundaries = jnp.array(boundaries)
  values = jnp.array(values)
  if not boundaries.ndim == values.ndim == 1:
    raise ValueError("boundaries and values must be sequences")
  if not boundaries.shape[0] == values.shape[0] - 1:
    raise ValueError("boundaries length must be one shorter than values length")

  def schedule(i):
    return values[jnp.sum(i > boundaries)]
  return schedule

def make_schedule(scalar_or_schedule: Union[float, Schedule]) -> Schedule:
  if callable(scalar_or_schedule):
    return scalar_or_schedule
  elif jnp.ndim(scalar_or_schedule) == 0:
    return constant(scalar_or_schedule)
  else:
    raise TypeError(type(scalar_or_schedule))


### utilities

def l2_norm(tree):
  """Compute the l2 norm of a pytree of arrays. Useful for weight decay."""
  leaves, _ = tree_flatten(tree)
  return jnp.sqrt(sum(jnp.vdot(x, x) for x in leaves))

def clip_grads(grad_tree, max_norm):
  """Clip gradients stored as a pytree of arrays to maximum norm `max_norm`."""
  norm = l2_norm(grad_tree)
  normalize = lambda g: jnp.where(norm < max_norm, g, g * (max_norm / norm))
  return tree_map(normalize, grad_tree)


### serialization utilities

class JoinPoint(object):
  """Marks the boundary between two joined (nested) pytrees."""
  def __init__(self, subtree):
    self.subtree = subtree

  # Since pytrees are containers of numpy arrays, look iterable.
  def __iter__(self):
    yield self.subtree

def unpack_optimizer_state(opt_state):
  """Converts an OptimizerState to a marked pytree.

  Converts an OptimizerState to a marked pytree with the leaves of the outer
  pytree represented as JoinPoints to avoid losing information. This function is
  intended to be useful when serializing optimizer states.

  Args:
    opt_state: An OptimizerState
  Returns:
    A pytree with JoinPoint leaves that contain a second level of pytrees.
  """
  states_flat, tree_def, subtree_defs = opt_state
  subtrees = map(tree_unflatten, subtree_defs, states_flat)
  sentinels = [JoinPoint(subtree) for subtree in subtrees]
  return tree_util.tree_unflatten(tree_def, sentinels)

def pack_optimizer_state(marked_pytree):
  """Converts a marked pytree to an OptimizerState.

  The inverse of unpack_optimizer_state. Converts a marked pytree with the
  leaves of the outer pytree represented as JoinPoints back into an
  OptimizerState. This function is intended to be useful when deserializing
  optimizer states.

  Args:
    marked_pytree: A pytree containing JoinPoint leaves that hold more pytrees.
  Returns:
    An equivalent OptimizerState to the input argument.
  """
  sentinels, tree_def = tree_flatten(marked_pytree)
  assert all(isinstance(s, JoinPoint) for s in sentinels)
  subtrees = [s.subtree for s in sentinels]
  states_flat, subtree_defs = unzip2(map(tree_flatten, subtrees))
  return OptimizerState(states_flat, tree_def, subtree_defs)
