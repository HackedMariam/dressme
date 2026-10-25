import React, { useEffect, useRef, useState } from 'react';
import { resizeImage } from '../api';
import Icon from './Icon';

/**
 * Live camera (getUserMedia): preview -> capture -> confirm.
 * Works on desktop webcams and phones (front/back switch). Falls back to a file picker.
 */
export default function CameraModal({ open, onClose, onCapture, title = 'Prendre une photo' }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [facing, setFacing] = useState('environment');
  const [error, setError] = useState(null);
  const [ready, setReady] = useState(false);
  const [shot, setShot] = useState(null);
  const [cameraCount, setCameraCount] = useState(0);

  const stop = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setReady(false);
  };

  useEffect(() => {
    if (!open || shot) return undefined;
    let cancelled = false;
    setError(null);

    (async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError("Ce navigateur ne donne pas accès à la caméra. Utilisez « Importer » à la place.");
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 960 } },
          audio: false,
        });
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }
        setReady(true);
        const devices = await navigator.mediaDevices.enumerateDevices();
        setCameraCount(devices.filter((d) => d.kind === 'videoinput').length);
      } catch (e) {
        const denied = e?.name === 'NotAllowedError' || e?.name === 'SecurityError';
        setError(denied
          ? "Accès à la caméra refusé. Autorisez la caméra dans la barre d'adresse du navigateur, puis réessayez."
          : e?.name === 'NotFoundError' ? 'Aucune caméra détectée sur cet appareil.' : `Caméra indisponible : ${e?.message || e}`);
      }
    })();

    return () => { cancelled = true; stop(); };
  }, [open, facing, shot]);

  useEffect(() => {
    if (!open) { setShot(null); setError(null); }
  }, [open]);

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    if (open) window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const capture = async () => {
    const video = videoRef.current;
    if (!video?.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    setShot(await resizeImage(canvas, 1024));
    stop();
  };

  const importFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (file) setShot(await resizeImage(file, 1024));
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="camera-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={title}>
        <header className="camera-header">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Fermer"><Icon name="close" /></button>
        </header>

        <div className="camera-stage">
          {shot ? (
            <img src={shot} alt="Photo capturée" />
          ) : error ? (
            <div className="camera-error">
              <Icon name="camera" size={40} />
              <p>{error}</p>
            </div>
          ) : (
            <>
              <video ref={videoRef} playsInline muted className={facing === 'user' ? 'mirrored' : ''} />
              {!ready && <div className="camera-loading"><span className="spinner" /> Ouverture de la caméra…</div>}
              {ready && <div className="camera-frame" aria-hidden="true" />}
            </>
          )}
        </div>

        <footer className="camera-actions">
          {shot ? (
            <>
              <button className="btn btn-ghost" onClick={() => setShot(null)}>Reprendre</button>
              <button className="btn btn-primary" onClick={() => { onCapture(shot); onClose(); }}>
                <Icon name="check" /> Utiliser cette photo
              </button>
            </>
          ) : (
            <>
              <label className="btn btn-ghost">
                <Icon name="upload" /> Importer
                <input type="file" accept="image/*" hidden onChange={importFile} />
              </label>
              <button className="shutter" onClick={capture} disabled={!ready} aria-label="Prendre la photo" />
              <button className="btn btn-ghost" disabled={!ready || cameraCount < 2}
                onClick={() => setFacing((f) => (f === 'environment' ? 'user' : 'environment'))}>
                <Icon name="switch" /> Changer
              </button>
            </>
          )}
        </footer>
      </div>
    </div>
  );
}
