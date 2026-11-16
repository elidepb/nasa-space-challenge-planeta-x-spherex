import numpy as np
from numpy.fft import fft2, ifft2, fftshift

def zogy_optimal_subtraction(
    img_new: np.ndarray, var_new: np.ndarray, psf_new: np.ndarray,
    img_ref: np.ndarray, var_ref: np.ndarray, psf_ref: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """
    Implementación del algoritmo ZOGY (Zackay, Ofek & Gal-Yam 2016)
    para sustracción libre de artefactos por asimetría de PSF en SPHEREx.
    Devuelve la imagen de diferencia (D) y el mapa de significancia estadística (S_corr / SNR).
    """
    # Reemplazar NaNs por mediana local (0 tras quitar fondo) para la FFT
    N = np.nan_to_num(img_new, nan=0.0)
    R = np.nan_to_num(img_ref, nan=0.0)

    sigma_n = float(np.nanmedian(np.sqrt(var_new)))
    sigma_r = float(np.nanmedian(np.sqrt(var_ref)))
    if sigma_n <= 0 or not np.isfinite(sigma_n):
        sigma_n = 1.0
    if sigma_r <= 0 or not np.isfinite(sigma_r):
        sigma_r = 1.0

    # Asegurar que las PSFs tengan el mismo tamaño que el cutout (Zero-padding)
    def pad_psf(psf, shape):
        padded = np.zeros(shape, dtype=np.float32)
        py, px = psf.shape
        cy, cx = shape[0] // 2, shape[1] // 2
        padded[cy - py//2 : cy - py//2 + py, cx - px//2 : cx - px//2 + px] = psf
        psf_sum = np.sum(psf)
        if psf_sum == 0:
            psf_sum = 1.0
        return fftshift(padded / psf_sum)

    Pn_hat = fft2(pad_psf(psf_new, N.shape))
    Pr_hat = fft2(pad_psf(psf_ref, R.shape))
    N_hat = fft2(N)
    R_hat = fft2(R)

    denom = np.sqrt((sigma_n**2) * (np.abs(Pr_hat)**2) + (sigma_r**2) * (np.abs(Pn_hat)**2) + 1e-12)
    
    # Imagen de diferencia en Fourier y su PSF efectiva
    D_hat = (Pr_hat * N_hat - Pn_hat * R_hat) / denom
    Pd_hat = (Pr_hat * Pn_hat) / (denom / np.sqrt(sigma_n**2 + sigma_r**2))

    # Mapa de estadístico de detección óptimo (Matched Filter SNR)
    S_hat = D_hat * np.conj(Pd_hat)
    
    diff_image = np.real(ifft2(D_hat))
    snr_map = np.real(ifft2(S_hat))
    return diff_image, snr_map
