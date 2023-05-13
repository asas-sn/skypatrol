import numpy as np
from astropy.timeseries import LombScargle
from tqdm.auto import tqdm

def LS_wavelet(tt, ff, x, y, e_y, Γ=2):

    """
    Computes a wavelet power spectrum. This is a *SLOW* implementation,
    hopefully to be replaced by something more efficient eventually.

    The units of tt and ff are assumed to be such that t * f is dimensionless.
    tt and x are assumed to have the same units.

    :param tt: Array of times at which to evaluate wavelet PS
    :param ff: Array of frequencies at which to evaluate wavelet PS
    :param x: Time axis of input time series
    :param y: Dynamical quantity (e.g. fluxes) of input time series
    :param e_y: Measurement errors of input time series
    :param Γ: tradeoff parameter between frequency and time resolution
              (by Fourier uncertainty principle). Larger values give
              better frequency resolution.

    :return: A numpy array containing the wavelet power spectrum.
    """

    # Instantiate accumulating array

    acc = np.full((len(tt), len(ff)), np.nan)

    # We will choose a "wavelet" that is essentially a Gaussian-modulated sinusoid.

    def window(x):
        return np.exp(-x**2/2)

    # Here we go!

    for j, ν in enumerate(tqdm(ff)):

        # The width of Gaussian modulation is chosen to be proportional
        # to the period of the modulated sinusoid, thus producing wavelet structure

        dt = Γ * (1/ν)
        for i, t in enumerate(tt):
            
            # we need to re-compute this for every combination of ν and t,
            # unfortunately.

            w = window((x-t)/dt)
            m = np.isfinite(np.nan_to_num(e_y/w, nan=np.inf))

            # actually compute the power: we use astropy's extirpolation-based L-S functionality.
            # rather than modifying the data points, we perform a weighted sum by
            # upweighting the uncertainties.

            # in principle we can get a massive performance improvement by using the NFFT
            # rather than the Press & Rybicki 1989 construction. Let's leave that for
            # later.

            ls = LombScargle(x[m], y[m], dy=(e_y/w)[m])
            p = float(ls.power(ν, normalization='psd'))

            # To preserve Parseval normalisation, we scale the power by the integral of the envelope,
            # which we can evaluate analytically. This allows us to recover a (blurred-out) Lomb-Scargle
            # periodogram when we integrate this with respect to time.

            p /= (np.sqrt(2 * np.pi) * dt)

            # Finally, we write this to the accumulating array.

            acc[i, j] = p
                
    return acc