import numpy as np
from numpy.testing import (assert_equal,
                           assert_almost_equal,
                           assert_array_almost_equal,
                           run_module_suite)


from dipy.core.optimize import Optimizer, SCIPY_LESS_0_12
import numpy.testing as npt


def func(x):

    return x[0]**2 + x[1]**2 + x[2]**2


def func2(x):

    return x[0]**2 + 0.5 * x[1]**2 + 0.2 * x[2]**2 + 0.2 * x[3]**2


@npt.dec.skipif(SCIPY_LESS_0_12)
def test_optimize_new_scipy():

    opt = Optimizer(fun=func, x0=np.array([1., 1., 1.]), method='Powell')

    assert_array_almost_equal(opt.xopt, np.array([0, 0, 0]))
    assert_almost_equal(opt.fopt, 0)

    opt = Optimizer(fun=func, x0=np.array([1., 1., 1.]), method='L-BFGS-B',
                    options={'maxcor': 10, 'ftol': 1e-7,
                             'gtol': 1e-5, 'eps': 1e-8})

    assert_array_almost_equal(opt.xopt, np.array([0, 0, 0]))
    assert_almost_equal(opt.fopt, 0)
    assert_equal(opt.evolution, None)

    assert_equal(opt.evolution, None)

    opt = Optimizer(fun=func, x0=np.array([1., 1., 1.]), method='L-BFGS-B',
                    options={'maxcor': 10, 'ftol': 1e-7,
                             'gtol': 1e-5, 'eps': 1e-8},
                    evolution=False)

    assert_array_almost_equal(opt.xopt, np.array([0, 0, 0]))
    assert_almost_equal(opt.fopt, 0)

    opt.print_summary()

    opt = Optimizer(fun=func2, x0=np.array([1., 1., 1., 5.]),
                    method='L-BFGS-B',
                    options={'maxcor': 10, 'ftol': 1e-7,
                             'gtol': 1e-5, 'eps': 1e-8},
                    evolution=True)

    assert_equal(opt.evolution.shape, (opt.nit, 4))

    opt = Optimizer(fun=func2, x0=np.array([1., 1., 1., 5.]),
                    method='Powell',
                    options={'xtol': 1e-6, 'ftol': 1e-6, 'maxiter': 1e6},
                    evolution=True)

    assert_array_almost_equal(opt.xopt, np.array([0, 0, 0, 0.]))


@npt.dec.skipif(not SCIPY_LESS_0_12)
def test_optimize_old_scipy():

    opt = Optimizer(fun=func, x0=np.array([1., 1., 1.]),
                    method='L-BFGS-B',
                    options={'maxcor': 10, 'ftol': 1e-7,
                             'gtol': 1e-5, 'eps': 1e-8})

    assert_array_almost_equal(opt.xopt, np.array([0, 0, 0]))
    assert_almost_equal(opt.fopt, 0)

    opt = Optimizer(fun=func2, x0=np.array([1., 1., 1., 5.]),
                    method='Powell',
                    options={'xtol': 1e-6, 'ftol': 1e-6, 'maxiter': 1e6},
                    evolution=True)

    assert_array_almost_equal(opt.xopt, np.array([0, 0, 0, 0.]))

    opt = Optimizer(fun=func, x0=np.array([1., 1., 1.]),
                    method='L-BFGS-B',
                    options={'maxcor': 10, 'eps': 1e-8})

    assert_array_almost_equal(opt.xopt, np.array([0, 0, 0]))
    assert_almost_equal(opt.fopt, 0)

    opt = Optimizer(fun=func, x0=np.array([1., 1., 1.]),
                    method='L-BFGS-B',
                    options=None)

    assert_array_almost_equal(opt.xopt, np.array([0, 0, 0]))
    assert_almost_equal(opt.fopt, 0)

    opt = Optimizer(fun=func2, x0=np.array([1., 1., 1., 5.]),
                    method='L-BFGS-B',
                    options={'gtol': 1e-7, 'ftol': 1e-7, 'maxiter': 10000})

    assert_array_almost_equal(opt.xopt, np.array([0, 0, 0, 0.]), 4)
    assert_almost_equal(opt.fopt, 0)

    opt = Optimizer(fun=func2, x0=np.array([1., 1., 1., 5.]),
                    method='Powell',
                    options={'maxiter': 1e6},
                    evolution=True)

    assert_array_almost_equal(opt.xopt, np.array([0, 0, 0, 0.]))

    opt = Optimizer(fun=func2, x0=np.array([1., 1., 1., 5.]),
                    method='Powell',
                    options={'maxiter': 1e6},
                    evolution=True)

    assert_array_almost_equal(opt.xopt, np.array([0, 0, 0, 0.]))


if __name__ == '__main__':

    run_module_suite()
