from __future__ import print_function
import numpy as np
from numpy.testing import (assert_equal,
                           assert_array_equal,
                           assert_array_almost_equal,
                           assert_raises)
import dipy.align.imwarp as imwarp
import dipy.align.metrics as metrics
import dipy.align.vector_fields as vfu
from dipy.data import get_data
from dipy.align import floating
import nibabel.eulerangles as eulerangles
from dipy.align.imwarp import DiffeomorphicMap
from dipy.align import VerbosityLevels

def test_mult_aff():
    r"""mult_aff from imwarp returns the matrix product A.dot(B) considering None
    as the identity
    """
    A = np.array([[1.0, 2.0], [3.0, 4.0]])
    B = np.array([[2.0, 0.0], [0.0, 2.0]])

    C = imwarp.mult_aff(A, B)
    expected_mult = np.array([[2.0, 4.0], [6.0, 8.0]])
    assert_array_almost_equal(C, expected_mult)

    C = imwarp.mult_aff(A, None)
    assert_array_almost_equal(C, A)

    C = imwarp.mult_aff(None, B)
    assert_array_almost_equal(C, B)

    C = imwarp.mult_aff(None, None)
    assert_equal(C, None)


def test_diffeomorphic_map_2d():
    r"""
    Creates a random displacement field that exactly maps pixels from an input
    image to an output image. First a discrete random assignment between the
    images is generated, then each pair of mapped points are transformed to
    the physical space by assigning a pair of arbitrary, fixed affine matrices
    to input and output images, and finaly the difference between their positions
    is taken as the displacement vector. The resulting displacement, although
    operating in physical space, maps the points exactly (up to numerical
    precision).
    """
    np.random.seed(2022966)
    domain_shape = (10, 10)
    codomain_shape = (10, 10)
    #create a simple affine transformation
    nr = domain_shape[0]
    nc = domain_shape[1]
    s = 1.1
    t = 0.25
    trans = np.array([[1, 0, -t*nr],
                      [0, 1, -t*nc],
                      [0, 0, 1]])
    trans_inv = np.linalg.inv(trans)
    scale = np.array([[1*s, 0, 0],
                      [0, 1*s, 0],
                      [0, 0, 1]])
    gt_affine = trans_inv.dot(scale.dot(trans))

    #create the random displacement field
    domain_affine = gt_affine
    codomain_affine = gt_affine
    disp, assign = vfu.create_random_displacement_2d(np.array(domain_shape, dtype=np.int32),
                                                     domain_affine,
                                                     np.array(codomain_shape, dtype=np.int32),
                                                     codomain_affine)
    disp = np.array(disp, dtype=floating)
    assign = np.array(assign)
    #create a random image (with decimal digits) to warp
    moving_image = np.ndarray(codomain_shape, dtype=floating)
    moving_image[...] = np.random.randint(0, 10, np.size(moving_image)).reshape(tuple(codomain_shape))
    #set boundary values to zero so we don't test wrong interpolation due to floating point precision
    moving_image[0,:] = 0
    moving_image[-1,:] = 0
    moving_image[:,0] = 0
    moving_image[:,-1] = 0

    #warp the moving image using the (exact) assignments
    expected = moving_image[(assign[...,0], assign[...,1])]

    #warp using a DiffeomorphicMap instance
    diff_map = imwarp.DiffeomorphicMap(2, domain_shape, domain_affine,
                                          domain_shape, domain_affine,
                                          codomain_shape, codomain_affine,
                                          None)
    diff_map.forward = disp

    #Verify that the transform method accepts different image types (note that
    #the actual image contained integer values, we don't want to test rounding)
    for type in [floating, np.float64, np.int64, np.int32]:
        moving_image = moving_image.astype(type)

        #warp using linear interpolation
        warped = diff_map.transform(moving_image, 'linear')
        #compare the images (the linear interpolation may introduce slight precision errors)
        assert_array_almost_equal(warped, expected, decimal=5)

        #Now test the nearest neighbor interpolation
        warped = diff_map.transform(moving_image, 'nearest')
        #compare the images (now we dont have to worry about precision, it is n.n.)
        assert_array_almost_equal(warped, expected)

        #verify the is_inverse flag
        inv = diff_map.inverse()
        warped = inv.transform_inverse(moving_image, 'linear')
        assert_array_almost_equal(warped, expected, decimal=5)

        warped = inv.transform_inverse(moving_image, 'nearest')
        assert_array_almost_equal(warped, expected)

    #Now test the inverse functionality
    diff_map = imwarp.DiffeomorphicMap(2, codomain_shape, codomain_affine,
                                          codomain_shape, codomain_affine,
                                          domain_shape, domain_affine, None)
    diff_map.backward = disp
    for type in [floating, np.float64, np.int64, np.int32]:
        moving_image = moving_image.astype(type)

        #warp using linear interpolation
        warped = diff_map.transform_inverse(moving_image, 'linear')
        #compare the images (the linear interpolation may introduce slight precision errors)
        assert_array_almost_equal(warped, expected, decimal=5)

        #Now test the nearest neighbor interpolation
        warped = diff_map.transform_inverse(moving_image, 'nearest')
        #compare the images (now we dont have to worry about precision, it is n.n.)
        assert_array_almost_equal(warped, expected)

    #Verify that DiffeomorphicMap raises the appropriate exceptions when
    #the sampling information is undefined
    diff_map = imwarp.DiffeomorphicMap(2, domain_shape, domain_affine,
                                          domain_shape, domain_affine,
                                          codomain_shape, codomain_affine,
                                          None)
    diff_map.forward = disp
    diff_map.domain_shape = None
    #If we don't provide the sampling info, it should try to use the map's info, but it's None...
    assert_raises(ValueError, diff_map.transform, moving_image, 'linear')

    #Same test for diff_map.transform_inverse
    diff_map = imwarp.DiffeomorphicMap(2, domain_shape, domain_affine,
                                          domain_shape, domain_affine,
                                          codomain_shape, codomain_affine,
                                          None)
    diff_map.forward = disp
    diff_map.codomain_shape = None
    #If we don't provide the sampling info, it should try to use the map's info, but it's None...
    assert_raises(ValueError, diff_map.transform_inverse, moving_image, 'linear')

    #We must provide, at least, the reference grid shape
    assert_raises(ValueError, imwarp.DiffeomorphicMap, 2, None)


def test_diffeomorphic_map_simplification_2d():
    r"""
    Create an invertible deformation field, and define a DiffeomorphicMap
    using different voxel-to-space transforms for domain, codomain, and
    reference discretizations, also use a non-identity pre-aligning matrix.
    Warp a circle using the diffeomorphic map to obtain the expected warped
    circle. Now simplify the DiffeomorphicMap and warp the same circle using
    this simplified map. Verify that the two warped circles are equal up to
    numerical precision.
    """
    #create a simple affine transformation
    domain_shape = (64, 64)
    codomain_shape = (80, 80)
    nr = domain_shape[0]
    nc = domain_shape[1]
    s = 1.1
    t = 0.25
    trans = np.array([[1, 0, -t*nr],
                      [0, 1, -t*nc],
                      [0, 0, 1]])
    trans_inv = np.linalg.inv(trans)
    scale = np.array([[1*s, 0, 0],
                      [0, 1*s, 0],
                      [0, 0, 1]])
    gt_affine = trans_inv.dot(scale.dot(trans))
    # Create the invertible displacement fields and the circle
    radius = 16
    circle = vfu.create_circle(codomain_shape[0], codomain_shape[1], radius)
    d, dinv = vfu.create_harmonic_fields_2d(domain_shape[0], domain_shape[1], 0.3, 6)
    #Define different voxel-to-space transforms for domain, codomain and reference grid,
    #also, use a non-identity pre-align transform
    D = gt_affine
    C = imwarp.mult_aff(gt_affine, gt_affine)
    R = np.eye(3)
    P = gt_affine

    #Create the original diffeomorphic map
    diff_map = imwarp.DiffeomorphicMap(2, domain_shape, R,
                                          domain_shape, D,
                                          codomain_shape, C,
                                          P)
    diff_map.forward = np.array(d, dtype = floating)
    diff_map.backward = np.array(dinv, dtype = floating)
    #Warp the circle to obtain the expected image
    expected = diff_map.transform(circle, 'linear')

    #Simplify
    simplified = diff_map.get_simplified_transform()
    #warp the circle
    warped = simplified.transform(circle, 'linear')
    #verify that the simplified map is equivalent to the
    #original one
    assert_array_almost_equal(warped, expected)
    #And of course, it must be simpler...
    assert_equal(simplified.domain_affine, None)
    assert_equal(simplified.codomain_affine, None)
    assert_equal(simplified.disp_affine, None)
    assert_equal(simplified.domain_affine_inv, None)
    assert_equal(simplified.codomain_affine_inv, None)
    assert_equal(simplified.disp_affine_inv, None)


def test_diffeomorphic_map_simplification_3d():
    r"""
    Create an invertible deformation field, and define a DiffeomorphicMap
    using different voxel-to-space transforms for domain, codomain, and
    reference discretizations, also use a non-identity pre-aligning matrix.
    Warp a sphere using the diffeomorphic map to obtain the expected warped
    sphere. Now simplify the DiffeomorphicMap and warp the same sphere using
    this simplified map. Verify that the two warped spheres are equal up to
    numerical precision.
    """
    #create a simple affine transformation
    domain_shape = (64, 64, 64)
    codomain_shape = (80, 80, 80)
    nr = domain_shape[0]
    nc = domain_shape[1]
    ns = domain_shape[2]
    s = 1.1
    t = 0.25
    trans = np.array([[1, 0, 0, -t*ns],
                      [0, 1, 0, -t*nr],
                      [0, 0, 1, -t*nc],
                      [0, 0, 0, 1]])
    trans_inv = np.linalg.inv(trans)
    scale = np.array([[1*s, 0, 0, 0],
                      [0, 1*s, 0, 0],
                      [0, 0, 1*s, 0],
                      [0, 0, 0, 1]])
    gt_affine = trans_inv.dot(scale.dot(trans))
    # Create the invertible displacement fields and the sphere
    radius = 16
    sphere = vfu.create_sphere(codomain_shape[0], codomain_shape[1], codomain_shape[2], radius)
    d, dinv = vfu.create_harmonic_fields_3d(domain_shape[0], domain_shape[1], domain_shape[2], 0.3, 6)
    #Define different voxel-to-space transforms for domain, codomain and reference grid,
    #also, use a non-identity pre-align transform
    D = gt_affine
    C = imwarp.mult_aff(gt_affine, gt_affine)
    R = np.eye(4)
    P = gt_affine

    #Create the original diffeomorphic map
    diff_map = imwarp.DiffeomorphicMap(3, domain_shape, R,
                                          domain_shape, D,
                                          codomain_shape, C,
                                          P)
    diff_map.forward = np.array(d, dtype = floating)
    diff_map.backward = np.array(dinv, dtype = floating)
    #Warp the sphere to obtain the expected image
    expected = diff_map.transform(sphere, 'linear')

    #Simplify
    simplified = diff_map.get_simplified_transform()
    #warp the sphere
    warped = simplified.transform(sphere, 'linear')
    #verify that the simplified map is equivalent to the
    #original one
    assert_array_almost_equal(warped, expected)
    #And of course, it must be simpler...
    assert_equal(simplified.domain_affine, None)
    assert_equal(simplified.codomain_affine, None)
    assert_equal(simplified.disp_affine, None)
    assert_equal(simplified.domain_affine_inv, None)
    assert_equal(simplified.codomain_affine_inv, None)
    assert_equal(simplified.disp_affine_inv, None)

def test_optimizer_exceptions():
    #An arbitrary valid metric
    metric = metrics.SSDMetric(2)
    # The metric must not be None
    assert_raises(ValueError, imwarp.SymmetricDiffeomorphicRegistration, None)
    # The iterations list must not be empty
    assert_raises(ValueError, imwarp.SymmetricDiffeomorphicRegistration, metric, [])

    optimizer = imwarp.SymmetricDiffeomorphicRegistration(metric, None)
    #Verify the default iterations list
    assert_array_equal(optimizer.level_iters, [100,100,25])

    #Verify exception thrown when attepting to fit the energy profile without enough data
    assert_raises(ValueError, optimizer._get_energy_derivative)


def test_scale_space_exceptions():
    np.random.seed(2022966)

    target_shape = (32, 32)
    #create a random image
    image = np.ndarray(target_shape, dtype=floating)
    image[...] = np.random.randint(0, 10, np.size(image)).reshape(tuple(target_shape))
    zeros = (image == 0).astype(np.int32)

    ss = imwarp.ScaleSpace(image,3)

    for invalid_level in [-1, 3, 4]:
        assert_raises(ValueError, ss.get_image, invalid_level)

    # Verify that the mask is correctly applied, when requested
    ss = imwarp.ScaleSpace(image,3, mask0=True)
    for level in range(3):
        img = ss.get_image(level)
        z = (img == 0).astype(np.int32)
        assert_array_equal(zeros, z)


def test_get_direction_and_spacings():
    xrot = 0.5
    yrot = 0.75
    zrot = 1.0
    direction_gt = eulerangles.euler2mat(zrot, yrot, xrot)
    spacings_gt = np.array([1.1, 1.2, 1.3])
    scaling_gt = np.diag(spacings_gt)
    translation_gt = np.array([1,2,3])

    affine = np.eye(4)
    affine[:3, :3] = direction_gt.dot(scaling_gt)
    affine[:3, 3] = translation_gt

    direction, spacings = imwarp.get_direction_and_spacings(affine, 3)
    assert_array_almost_equal(direction, direction_gt)
    assert_array_almost_equal(spacings, spacings_gt)

def simple_callback(sdr, status):
    if status == imwarp.RegistrationStages.INIT_START:
        sdr.INIT_START_CALLED = 1
    if status == imwarp.RegistrationStages.INIT_END:
        sdr.INIT_END_CALLED = 1
    if status == imwarp.RegistrationStages.OPT_START:
        sdr.OPT_START_CALLED = 1
    if status == imwarp.RegistrationStages.OPT_END:
        sdr.OPT_END_CALLED = 1
    if status == imwarp.RegistrationStages.SCALE_START:
        sdr.SCALE_START_CALLED = 1
    if status == imwarp.RegistrationStages.SCALE_END:
        sdr.SCALE_END_CALLED = 1
    if status == imwarp.RegistrationStages.ITER_START:
        sdr.ITER_START_CALLED = 1
    if status == imwarp.RegistrationStages.ITER_END:
        sdr.ITER_END_CALLED = 1


def test_ssd_2d_demons():
    r'''
    Classical Circle-To-C experiment for 2D Monomodal registration. This test
    is intended to detect regressions only: we saved the energy profile (the
    sequence of energy values at each iteration) of a working version of SSD in
    2D using the Demons step, and this test checks that the current energy
    profile matches the saved one.
    '''
    fname_moving = get_data('reg_o')
    fname_static = get_data('reg_c')

    moving = np.load(fname_moving)
    static = np.load(fname_static)
    moving = np.array(moving, dtype=floating)
    static = np.array(static, dtype=floating)
    moving = (moving-moving.min())/(moving.max() - moving.min())
    static = (static-static.min())/(static.max() - static.min())
    #Create the SSD metric
    smooth = 4
    step_type = 'demons'
    similarity_metric = metrics.SSDMetric(2, smooth=smooth, step_type=step_type)

    #Configure and run the Optimizer
    level_iters = [200, 100, 50, 25]
    step_length = 0.25
    opt_tol = 1e-4
    inv_iter = 40
    inv_tol = 1e-3
    ss_sigma_factor = 0.2
    optimizer = imwarp.SymmetricDiffeomorphicRegistration(similarity_metric,
        level_iters, step_length, ss_sigma_factor, opt_tol, inv_iter, inv_tol)

    #test callback being called
    optimizer.INIT_START_CALLED = 0
    optimizer.INIT_END_CALLED = 0
    optimizer.OPT_START_CALLED = 0
    optimizer.OPT_END_CALLED = 0
    optimizer.SCALE_START_CALLED = 0
    optimizer.SCALE_END_CALLED = 0
    optimizer.ITER_START_CALLED = 0
    optimizer.ITER_END_CALLED = 0

    optimizer.callback_counter_test = 0
    optimizer.callback = simple_callback

    optimizer.verbosity = VerbosityLevels.DEBUG
    mapping = optimizer.optimize(static, moving, None)
    m = optimizer.get_map()
    assert_equal(mapping, m)

    subsampled_energy_profile = np.array(optimizer.full_energy_profile[::10])
    if floating is np.float32:
        expected_profile = \
            np.array([312.6813333, 162.57756447, 99.2766679, 77.38698935,
                      61.75415204, 55.37420428, 46.36872571, 41.81811505,
                      36.38683617, 33.03952963, 30.91409901, 54.41447237,
                      23.40232241, 12.75092466, 10.19231733, 9.21058037,
                      57.4636143, 38.94004856, 36.26093212, 108.0136453,
                      81.35521049, 74.61956833])
    else:
        expected_profile = \
            np.array([312.68133361, 162.57744066, 99.27669798, 77.38683186,
                      61.75391429, 55.3740711, 46.36870776, 41.81809239,
                      36.3898153, 32.78365961, 30.69843811, 53.67073767,
                      21.74630524, 11.98102583, 11.51086685, 55.30707781,
                      39.88467545, 34.29444978, 33.10822964, 122.64743831,
                      84.18144073, 75.60088687])

    assert_array_almost_equal(subsampled_energy_profile, expected_profile)
    assert_equal(optimizer.OPT_START_CALLED, 1)
    assert_equal(optimizer.OPT_END_CALLED, 1)
    assert_equal(optimizer.SCALE_START_CALLED, 1)
    assert_equal(optimizer.SCALE_END_CALLED, 1)
    assert_equal(optimizer.ITER_START_CALLED, 1)
    assert_equal(optimizer.ITER_END_CALLED, 1)



def test_ssd_2d_gauss_newton():
    r'''
    Classical Circle-To-C experiment for 2D Monomodal registration. This test
    is intended to detect regressions only: we saved the energy profile (the
    sequence of energy values at each iteration) of a working version of SSD in
    2D using the Gauss Newton step, and this test checks that the current energy
    profile matches the saved one.
    '''
    fname_moving = get_data('reg_o')
    fname_static = get_data('reg_c')

    moving = np.load(fname_moving)
    static = np.load(fname_static)
    moving = np.array(moving, dtype=floating)
    static = np.array(static, dtype=floating)
    moving = (moving-moving.min())/(moving.max() - moving.min())
    static = (static-static.min())/(static.max() - static.min())
    #Create the SSD metric
    smooth = 4
    inner_iter = 5
    step_type = 'gauss_newton'
    similarity_metric = metrics.SSDMetric(2, smooth, inner_iter, step_type)

    #Configure and run the Optimizer
    level_iters = [200, 100, 50, 25]
    step_length = 0.5
    opt_tol = 1e-4
    inv_iter = 40
    inv_tol = 1e-3
    ss_sigma_factor = 0.2
    optimizer = imwarp.SymmetricDiffeomorphicRegistration(similarity_metric,
        level_iters, step_length, ss_sigma_factor, opt_tol, inv_iter, inv_tol)

    #test callback not being called
    optimizer.INIT_START_CALLED = 0
    optimizer.INIT_END_CALLED = 0
    optimizer.OPT_START_CALLED = 0
    optimizer.OPT_END_CALLED = 0
    optimizer.SCALE_START_CALLED = 0
    optimizer.SCALE_END_CALLED = 0
    optimizer.ITER_START_CALLED = 0
    optimizer.ITER_END_CALLED = 0

    optimizer.verbosity = VerbosityLevels.DEBUG
    mapping = optimizer.optimize(static, moving, np.eye(3), np.eye(3), np.eye(3))
    m = optimizer.get_map()
    assert_equal(mapping, m)
    subsampled_energy_profile = np.array(optimizer.full_energy_profile[::10])
    if floating is np.float32:
        expected_profile = \
            np.array([312.68133316, 79.40404517, 23.3715698, 125.02700267,
                      59.79982213, 34.64971733, 23.37131446, 171.28250576,
                      62.22266377, 125.24392168])
    else:
        expected_profile = \
            np.array([312.68133361, 79.40404354, 23.34588446, 124.3247997,
                      61.69601973, 38.15047181, 23.53315113, 80.0791295,
                      57.21700113, 143.73270476])
    assert_array_almost_equal(subsampled_energy_profile, expected_profile)
    assert_equal(optimizer.OPT_START_CALLED, 0)
    assert_equal(optimizer.OPT_END_CALLED, 0)
    assert_equal(optimizer.SCALE_START_CALLED, 0)
    assert_equal(optimizer.SCALE_END_CALLED, 0)
    assert_equal(optimizer.ITER_START_CALLED, 0)
    assert_equal(optimizer.ITER_END_CALLED, 0)


def get_synthetic_warped_circle(nslices):
    #get a subsampled circle
    fname_cicle = get_data('reg_o')
    circle = np.load(fname_cicle)[::4,::4].astype(floating)

    #create a synthetic invertible map and warp the circle
    d, dinv = vfu.create_harmonic_fields_2d(64, 64, 0.1, 4)
    d = np.asarray(d, dtype=floating)
    dinv = np.asarray(dinv, dtype=floating)
    mapping = DiffeomorphicMap(2, (64, 64))
    mapping.forward, mapping.backward = d, dinv
    wcircle = mapping.transform(circle)

    if(nslices == 1):
        return circle, wcircle

    #normalize and form the 3d by piling slices
    circle = (circle-circle.min())/(circle.max() - circle.min())
    circle_3d = np.ndarray(circle.shape + (nslices,), dtype=floating)
    circle_3d[...] = circle[...,None]
    circle_3d[...,0] = 0
    circle_3d[...,-1] = 0

    #do the same with the warped circle
    wcircle = (wcircle-wcircle.min())/(wcircle.max() - wcircle.min())
    wcircle_3d = np.ndarray(wcircle.shape + (nslices,), dtype=floating)
    wcircle_3d[...] = wcircle[...,None]
    wcircle_3d[...,0] = 0
    wcircle_3d[...,-1] = 0

    return circle_3d, wcircle_3d


def test_ssd_3d_demons():
    r'''
    Register a stack of circles ('cylinder') before and after warping them with
    a synthetic diffeomorphism. This test is intended to detect regressions
    only: we saved the energy profile (the sequence of energy values at each
    iteration) of a working version of SSD in 3D using the Demons step, and this
    test checks that the current energy profile matches the saved one. The
    validation of the "working version" was done by registering the 18 manually
    annotated T1 brain MRI database IBSR with each other and computing the
    jaccard index for all 31 common anatomical regions.
    '''
    moving, static = get_synthetic_warped_circle(30)
    moving[...,:8] = 0
    moving[...,-1:-9:-1] = 0
    static[...,:8] = 0
    static[...,-1:-9:-1] = 0

    #Create the SSD metric
    smooth = 4
    step_type = 'demons'
    similarity_metric = metrics.SSDMetric(3, smooth=smooth, step_type=step_type)

    #Create the optimizer
    level_iters = [10, 5]
    step_length = 0.25
    opt_tol = 1e-4
    inv_iter = 20
    inv_tol = 1e-3
    ss_sigma_factor = 0.5
    optimizer = imwarp.SymmetricDiffeomorphicRegistration(similarity_metric,
        level_iters, step_length, ss_sigma_factor, opt_tol, inv_iter, inv_tol)
    optimizer.verbosity = VerbosityLevels.DEBUG
    mapping = optimizer.optimize(static, moving, None)
    m = optimizer.get_map()
    assert_equal(mapping, m)
    energy_profile = np.array(optimizer.full_energy_profile)
    if floating is np.float32:
        expected_profile = \
            np.array([312.22706987, 154.65556885, 53.88594419, 9.22626825,
                      36.50370933, 13.54829978, 49.57619437, 15.71122527,
                      53.45897119, 15.62018739, 521.95785712, 158.16217928,
                      182.49116432, 144.91081752, 176.6810387])
    else:
        expected_profile = \
            np.array([312.22709468, 154.65706498, 53.8856324, 8.90160898,
                      34.91911552, 12.66043296, 49.61341791, 15.14198327,
                      52.25467529, 18.88243845, 490.48088231, 149.29027701,
                      192.26219053, 137.5291187, 187.2795753])
    assert_array_almost_equal(energy_profile, expected_profile, decimal=6)


def test_ssd_3d_gauss_newton():
    r'''
    Register a stack of circles ('cylinder') before and after warping them with
    a synthetic diffeomorphism. This test is intended to detect regressions
    only: we saved the energy profile (the sequence of energy values at each
    iteration) of a working version of SSD in 3D using the Gauss-Newton step,
    and this test checks that the current energy profile matches the saved
    one. The validation of the "working version" was
    done by registering the 18 manually annotated T1 brain MRI database IBSR
    with each other and computing the jaccard index for all 31 common anatomical
    regions.
    '''
    moving, static = get_synthetic_warped_circle(35)
    moving[...,:10] = 0
    moving[...,-1:-11:-1] = 0
    static[...,:10] = 0
    static[...,-1:-11:-1] = 0

    #Create the SSD metric
    smooth = 4
    inner_iter = 5
    step_type = 'gauss_newton'
    similarity_metric = metrics.SSDMetric(3, smooth, inner_iter, step_type)

    #Create the optimizer
    level_iters = [10, 5]
    step_length = 0.25
    opt_tol = 1e-4
    inv_iter = 20
    inv_tol = 1e-3
    ss_sigma_factor = 0.5
    optimizer = imwarp.SymmetricDiffeomorphicRegistration(similarity_metric,
        level_iters, step_length, ss_sigma_factor, opt_tol, inv_iter, inv_tol)
    optimizer.verbosity = VerbosityLevels.DEBUG
    mapping = optimizer.optimize(static, moving, None)
    m = optimizer.get_map()
    assert_equal(mapping, m)
    energy_profile = np.array(optimizer.full_energy_profile)
    if floating is np.float32:
        expected_profile = \
            np.array([348.32047209927373, 143.49111863234222, 44.328151771258206,
                      8.759564367010988, 3.1378191742723662, 14.846951961939153,
                      6.405154727081836, 20.437036950018083, 17.399044912417597,
                      49.072929423423496, 269.2553956858318, 80.72079256138973,
                      200.242742072974, 68.21238489882822, 208.28730597575378])
    else:
        expected_profile = \
            np.array([348.32049916992855, 143.49111631974688, 44.328145727486174,
                      8.759562612294948, 3.137819214539283, 14.846929648490525,
                      6.405154001052728, 20.437123731745928, 17.39892098642616,
                      49.07339619667625, 269.2533380585498, 80.72162511785703,
                      200.24505477294477, 68.21183884286609, 208.29025925025073])
    assert_array_almost_equal(energy_profile, expected_profile, decimal=6)


def test_cc_2d():
    r'''
    Register a circle to itself after warping it under a synthetic invertible
    map. This test is intended to detect regressions only: we saved the energy
    profile (the sequence of energy values at each iteration) of a working
    version of CC in 2D, and this test checks that the current energy profile
    matches the saved one.
    '''

    moving, static = get_synthetic_warped_circle(1)
    #Configure the metric
    sigma_diff = 3.0
    radius = 4
    metric = metrics.CCMetric(2, sigma_diff, radius)

    #Configure and run the Optimizer
    level_iters = [10, 5]
    optimizer = imwarp.SymmetricDiffeomorphicRegistration(metric, level_iters)
    optimizer.verbosity = VerbosityLevels.DEBUG
    mapping = optimizer.optimize(static, moving, None)
    m = optimizer.get_map()
    assert_equal(mapping, m)
    energy_profile = np.array(optimizer.full_energy_profile)
    if floating is np.float32:
        expected_profile = \
            [-681.02276236, -920.57714783, -1006.81657463, -1025.83920278,
             -1018.48108319, -1018.45000627, -1005.09703188, -1012.69584487,
             -1016.42673146, -998.88289898, -2788.28110913, -2829.93521983,
             -2823.50737329, -2840.70676978, -2805.36486487]
    else:
        expected_profile = \
            [-685.02275452, -928.57719958, -1018.81655195, -1025.39899865,
             -1002.72673624, -1009.50734392, -1017.17915308, -999.55456055,
             -1025.76154939, -994.94755395, -2784.70111646, -2820.40702267,
             -2801.45275665, -2822.69658715, -2813.39864684]
    expected_profile = np.asarray(expected_profile)
    assert_array_almost_equal(energy_profile, expected_profile)


def test_cc_3d():
    r'''
    Register a stack of circles ('cylinder') before and after warping them with
    a synthetic diffeomorphism. This test
    is intended to detect regressions only: we saved the energy profile (the
    sequence of energy values at each iteration) of a working version of CC in
    3D, and this test checks that the current energy profile matches the saved
    one. The validation of the "working version" was
    done by registering the 18 manually annotated T1 brain MRI database IBSR
    with each other and computing the jaccard index for all 31 common anatomical
    regions. The "working version" of CC in 3D obtains very similar results as
    those reported for ANTS on the same database with the same number of
    iterations. Any modification that produces a change in the energy profile
    should be carefully validated to ensure no accuracy loss.
    '''
    moving, static = moving, static = get_synthetic_warped_circle(20)

    #Create the CC metric
    sigma_diff = 2.0
    radius = 4
    similarity_metric = metrics.CCMetric(3, sigma_diff, radius)

    #Create the optimizer
    level_iters = [20, 10]
    step_length = 0.25
    opt_tol = 1e-4
    inv_iter = 20
    inv_tol = 1e-3
    ss_sigma_factor = 0.5
    optimizer = imwarp.SymmetricDiffeomorphicRegistration(similarity_metric,
        level_iters, step_length, ss_sigma_factor, opt_tol, inv_iter, inv_tol)
    optimizer.verbosity = VerbosityLevels.DEBUG

    mapping = optimizer.optimize(static, moving, None, None, None)
    m = optimizer.get_map()
    assert_equal(mapping, m)
    energy_profile = np.array(optimizer.full_energy_profile)*1e-4
    if floating is np.float32:
        expected_profile = \
            [-0.17136006, -0.1927569, -0.20436096, -0.20785162, -0.20389074,
             -0.20924245, -0.20703476, -0.20914331, -0.20797673, -0.20894931,
             -0.20861396, -0.20884857, -0.20867266, -0.20892447, -0.20721796,
             -0.20964756, -3.03669258, -3.08002058, -3.07073973, -3.06754953,
             -3.06459596, -3.08409787, -3.08325558, -3.08083075, -3.08227744,
             -3.08802501]
    else:
        expected_profile = \
            [-0.17416006, -0.1937569, -0.20776097, -0.21125163, -0.20709075,
             -0.21184246, -0.21003478, -0.21214333, -0.21117674, -0.21194933,
             -0.21141397, -0.21184858, -0.21147268, -0.21232447, -0.211618,
             -0.21264758, -3.13589338, -3.29324761, -3.3906351, -3.46849833,
             -3.51429254, -3.51747425, -3.5175145, -3.52346059, -3.51608344,
             -3.53157882]
    expected_profile = np.asarray(expected_profile)
    assert_array_almost_equal(energy_profile, expected_profile, decimal=6)


def test_em_3d_gauss_newton():
    r'''
    Register a stack of circles ('cylinder') before and after warping them with
    a synthetic diffeomorphism. This test
    is intended to detect regressions only: we saved the energy profile (the
    sequence of energy values at each iteration) of a working version of EM in
    3D, and this test checks that the current energy profile matches the saved
    one. The validation of the "working version" was
    done by registering the 18 manually annotated T1 brain MRI database IBSR
    with each other and computing the jaccard index for all 31 common anatomical
    regions. The "working version" of EM in 3D obtains very similar results as
    those reported for ANTS on the same database. Any modification that produces
    a change in the energy profile should be carefully validated to ensure no
    accuracy loss.
    '''
    moving, static = get_synthetic_warped_circle(30)
    moving[...,:8] = 0
    moving[...,-1:-9:-1] = 0
    static[...,:8] = 0
    static[...,-1:-9:-1] = 0

    #Create the EM metric
    smooth=25.0
    inner_iter=20
    step_length=0.25
    q_levels=256
    double_gradient=True
    iter_type='gauss_newton'
    similarity_metric = metrics.EMMetric(
        3, smooth, inner_iter, q_levels, double_gradient, iter_type)

    #Create the optimizer
    level_iters = [10, 5]
    opt_tol = 1e-4
    inv_iter = 20
    inv_tol = 1e-3
    ss_sigma_factor = 0.5
    optimizer = imwarp.SymmetricDiffeomorphicRegistration(similarity_metric,
        level_iters, step_length, ss_sigma_factor, opt_tol, inv_iter, inv_tol)
    optimizer.verbosity = VerbosityLevels.DEBUG
    mapping = optimizer.optimize(static, moving, None)
    m = optimizer.get_map()
    assert_equal(mapping, m)
    energy_profile = np.array(optimizer.full_energy_profile)
    if floating is np.float32:
        expected_profile = \
            np.array([144.03694724, 63.06898905, 51.84577681, 39.75409677,
                      32.10342869, 44.84663951, 38.48587153, 36.64351228, 
                      37.14853803, 40.07766093, 1686.24351443, 1500.19633766,
                      1302.04852831, 1148.19549508, 1032.820053])
    else:
        expected_profile = \
            np.array([144.03695787, 63.06894122, 51.84575143, 39.75308705,
                      32.13062096, 44.15214831, 40.71952511, 37.26523679,
                      37.86654915, 34.92844873, 1644.56890565, 1408.15872151,
                      1274.1339093, 1131.38037004, 1004.71854514])
    assert_array_almost_equal(energy_profile, expected_profile, decimal=6)


def test_em_2d_gauss_newton():
    r'''
    Register a circle to itself after warping it under a synthetic invertible
    map. This test is intended to detect regressions only: we saved the energy
    profile (the sequence of energy values at each iteration) of a working
    version of EM in 2D, and this test checks that the current energy profile
    matches the saved one.
    '''

    moving, static = get_synthetic_warped_circle(1)

    #Configure the metric
    smooth=25.0
    inner_iter=20
    q_levels=256
    double_gradient=False
    iter_type='gauss_newton'
    metric = metrics.EMMetric(
        2, smooth, inner_iter, q_levels, double_gradient, iter_type)

    #Configure and run the Optimizer
    level_iters = [40, 20, 10]
    optimizer = imwarp.SymmetricDiffeomorphicRegistration(metric, level_iters)
    optimizer.verbosity = VerbosityLevels.DEBUG
    mapping = optimizer.optimize(static, moving, None)
    m = optimizer.get_map()
    assert_equal(mapping, m)
    energy_profile = np.array(optimizer.full_energy_profile)[::4]
    if floating is np.float32:
        expected_profile = \
            [2.50773392e+00, 1.19082175e+00, 3.44192871e-01, 4.26320783e-01,
             3.77910892e-02, 3.34404847e-01, 3.00400618e+00, 2.56292691e+00,
             2.10458398e+00, 2.45479897e+00, 6.14513257e+01, 5.38091115e+01,
             5.27868250e+01]
    else:
        expected_profile = \
            [2.50773436, 1.19082577, 0.34422934, 0.19543193, 0.23659461,
             0.41145348, 3.56414698, 3.02325691, 1.74649377, 1.8172007,
             2.09930208, 53.06513917, 49.4088898 ]
    assert_array_almost_equal(energy_profile, np.array(expected_profile))


def test_em_3d_demons():
    r'''
    Register a stack of circles ('cylinder') before and after warping them with
    a synthetic diffeomorphism. This test
    is intended to detect regressions only: we saved the energy profile (the
    sequence of energy values at each iteration) of a working version of EM in
    3D, and this test checks that the current energy profile matches the saved
    one. The validation of the "working version" was
    done by registering the 18 manually annotated T1 brain MRI database IBSR
    with each other and computing the jaccard index for all 31 common anatomical
    regions. The "working version" of EM in 3D obtains very similar results as
    those reported for ANTS on the same database. Any modification that produces
    a change in the energy profile should be carefully validated to ensure no
    accuracy loss.
    '''
    moving, static = get_synthetic_warped_circle(30)
    moving[...,:8] = 0
    moving[...,-1:-9:-1] = 0
    static[...,:8] = 0
    static[...,-1:-9:-1] = 0

    #Create the EM metric
    smooth=25.0
    inner_iter=20
    step_length=0.25
    q_levels=256
    double_gradient=True
    iter_type='demons'
    similarity_metric = metrics.EMMetric(
        3, smooth, inner_iter, q_levels, double_gradient, iter_type)

    #Create the optimizer
    level_iters = [10, 5]
    opt_tol = 1e-4
    inv_iter = 20
    inv_tol = 1e-3
    ss_sigma_factor = 0.5
    optimizer = imwarp.SymmetricDiffeomorphicRegistration(similarity_metric,
        level_iters, step_length, ss_sigma_factor, opt_tol, inv_iter, inv_tol)
    optimizer.verbosity = VerbosityLevels.DEBUG
    mapping = optimizer.optimize(static, moving, None)
    m = optimizer.get_map()
    assert_equal(mapping, m)
    energy_profile = np.array(optimizer.full_energy_profile)
    if floating is np.float32:
        expected_profile = \
            np.array([144.0369470764622, 122.39543007604394, 112.43783718421119,
                      85.46819602604248, 101.15549228031932, 119.62429965589826,
                      124.00100190950647, 118.94404608675168, 112.57666071129853,
                      117.84424645441413, 4470.2719430621, 4138.201850019068,
                      4007.225585554024, 4074.8853855654797, 3833.6272345908865])
    else:
        expected_profile = \
            np.array([144.03695786872666, 121.73922862297613, 107.41132697303448,
                      90.70731102557508, 97.4295175632117, 112.78404966709469,
                      103.29910157963684, 111.83865866152108, 121.26265581989485,
                      118.19913094423933, 4222.003181977351, 4418.042311441615,
                      4508.671160627819, 4761.251133428944, 4292.8507317299245])
    assert_array_almost_equal(energy_profile, expected_profile, decimal=6)


def test_em_2d_demons():
    r'''
    Register a circle to itself after warping it under a synthetic invertible
    map. This test is intended to detect regressions only: we saved the energy
    profile (the sequence of energy values at each iteration) of a working
    version of EM in 2D, and this test checks that the current energy profile
    matches the saved one.
    '''

    moving, static = get_synthetic_warped_circle(1)

    #Configure the metric
    smooth=25.0
    inner_iter=20
    q_levels=256
    double_gradient=False
    iter_type='demons'
    metric = metrics.EMMetric(
        2, smooth, inner_iter, q_levels, double_gradient, iter_type)

    #Configure and run the Optimizer
    level_iters = [40, 20, 10]
    optimizer = imwarp.SymmetricDiffeomorphicRegistration(metric, level_iters)
    optimizer.verbosity = VerbosityLevels.DEBUG
    mapping = optimizer.optimize(static, moving, None)
    m = optimizer.get_map()
    assert_equal(mapping, m)
    energy_profile = np.array(optimizer.full_energy_profile)[::2]
    if floating is np.float32:
        expected_profile = \
            [2.50773393, 4.59842633, 3.94307794, 3.09777134, 2.57982865,
             3.24937725, 0.42507437, 2.59523238, 29.8114103, 34.94621044,
             27.49480758, 38.64567224, 28.14442977, 25.34123425, 36.95076494,
             192.36444764, 202.90168694, 188.44310016, 199.73662253, 193.81159141]
    else:
        expected_profile = \
            [2.50773436, 4.59843299, 3.94307817, 3.09777401, 2.57983375,
             3.24936765, 0.42506361, 2.5952175, 29.81143768, 33.42148555,
             29.04341476, 29.44541313, 27.39435491, 27.62029669, 187.34889413,
             206.57998934, 198.48724278, 188.65410869, 177.83943006]
    assert_array_almost_equal(energy_profile, np.array(expected_profile))

if __name__=='__main__':
    test_scale_space_exceptions()
    test_optimizer_exceptions()
    test_mult_aff()
    test_diffeomorphic_map_2d()
    test_diffeomorphic_map_simplification_2d()
    test_diffeomorphic_map_simplification_3d()
    test_get_direction_and_spacings()
    test_ssd_2d_demons()
    test_ssd_2d_gauss_newton()
    test_ssd_3d_demons()
    test_ssd_3d_gauss_newton()
    test_cc_2d()
    test_cc_3d()
    test_em_2d_gauss_newton()
    test_em_3d_gauss_newton()
    test_em_3d_demons()
    test_em_2d_demons()
