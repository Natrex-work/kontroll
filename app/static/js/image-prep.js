/**
 * Image-prep: bildekomprimering og EXIF-orientering før lokal lagring.
 *
 * Hovedmål: kraftig redusere lagringsbruk og opplastingstid, og fjerne
 * vanligste årsak til synkfeil (for store filer over mobilnett).
 *
 * Denne modulen monkey-patcher KVLocalMedia.put() slik at alle bilder
 * automatisk komprimeres og roteres riktig før de lagres i IndexedDB.
 * Kontrollskjema (case-app.js) trenger ingen endringer — komprimeringen
 * skjer transparent i mediepipelinen.
 *
 * Audio passeres uendret. Filer som allerede er små (< 400 KB) eller
 * ikke er bilder hoppes over.
 */
(function () {
  'use strict';

  if (window.KVImagePrep) return;

  var DEFAULT_MAX_DIMENSION = 1920;
  var DEFAULT_QUALITY = 0.85;
  var SKIP_IF_BYTES_BELOW = 400 * 1024; // 400 KB
  var COMPRESSED_MIME = 'image/jpeg';

  function isImageFile(file) {
    if (!file) return false;
    var type = String(file.type || '').toLowerCase();
    if (type.indexOf('image/') !== 0) return false;
    // Don't try to recompress SVG (vector) or HEIC (no decoder in older Safari)
    if (type === 'image/svg+xml') return false;
    return true;
  }

  function readImageBitmap(blob) {
    // Prefer createImageBitmap (handles EXIF orientation natively in Safari 16+, Chrome)
    if (typeof createImageBitmap === 'function') {
      return createImageBitmap(blob, { imageOrientation: 'from-image' })
        .catch(function () {
          // Older Safari may not support imageOrientation option — fall back
          return createImageBitmap(blob);
        });
    }
    return Promise.reject(new Error('createImageBitmap er ikke tilgjengelig'));
  }

  function readViaImage(blob) {
    // Fallback for environments without createImageBitmap
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(blob);
      var img = new Image();
      img.onload = function () {
        URL.revokeObjectURL(url);
        resolve(img);
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        reject(new Error('Kunne ikke laste bilde for komprimering'));
      };
      img.src = url;
    });
  }

  function getDimensions(source) {
    if (source && typeof source.width === 'number' && typeof source.height === 'number') {
      return { w: source.width, h: source.height };
    }
    return { w: source.naturalWidth || 0, h: source.naturalHeight || 0 };
  }

  function compressImage(blob, options) {
    options = options || {};
    var maxDim = Math.max(320, Math.min(4096, Number(options.maxDimension) || DEFAULT_MAX_DIMENSION));
    var quality = Math.max(0.5, Math.min(0.95, Number(options.quality) || DEFAULT_QUALITY));

    if (!blob || !isImageFile(blob)) return Promise.resolve(blob);
    if (Number(blob.size || 0) < SKIP_IF_BYTES_BELOW) return Promise.resolve(blob);

    return readImageBitmap(blob)
      .catch(function () { return readViaImage(blob); })
      .then(function (source) {
        var dims = getDimensions(source);
        if (!dims.w || !dims.h) {
          // Could not measure — return original
          if (source.close) source.close();
          return blob;
        }

        var longest = Math.max(dims.w, dims.h);
        var scale = longest > maxDim ? (maxDim / longest) : 1;
        var width = Math.max(1, Math.round(dims.w * scale));
        var height = Math.max(1, Math.round(dims.h * scale));

        var canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        var ctx = canvas.getContext('2d');
        if (!ctx) {
          if (source.close) source.close();
          return blob;
        }

        // White background for transparent PNGs being converted to JPEG
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, width, height);
        try {
          ctx.drawImage(source, 0, 0, width, height);
        } catch (e) {
          if (source.close) source.close();
          return blob;
        }
        if (source.close) source.close();

        return new Promise(function (resolve) {
          canvas.toBlob(function (out) {
            if (!out) { resolve(blob); return; }
            // Only return the compressed version if it's actually smaller
            if (Number(out.size || 0) >= Number(blob.size || 0)) {
              resolve(blob);
            } else {
              resolve(out);
            }
          }, COMPRESSED_MIME, quality);
        });
      })
      .catch(function () {
        // Any error → return original; we don't want to block the user
        return blob;
      });
  }

  function blobToFileLike(blob, originalFile) {
    if (!blob) return null;
    if (blob === originalFile) return originalFile;
    // Build a File so the rest of the pipeline (which expects .name/.lastModified) works
    try {
      var name = (originalFile && originalFile.name) || ('bilde-' + Date.now() + '.jpg');
      // If we converted to JPEG, ensure extension matches
      if (blob.type && blob.type.indexOf('image/jpeg') === 0 && !/\.jpe?g$/i.test(name)) {
        name = name.replace(/\.[a-z0-9]+$/i, '') + '.jpg';
      }
      return new File([blob], name, {
        type: blob.type || (originalFile && originalFile.type) || COMPRESSED_MIME,
        lastModified: Date.now()
      });
    } catch (e) {
      // Older browsers without File constructor
      try { blob.name = (originalFile && originalFile.name) || ('bilde-' + Date.now() + '.jpg'); } catch (e2) {}
      return blob;
    }
  }

  /**
   * Public API: compress if file is an image, else passthrough.
   * Returns a Promise<File|Blob>.
   */
  function prepareIfImage(file, options) {
    if (!isImageFile(file)) return Promise.resolve(file);
    return compressImage(file, options).then(function (out) {
      return blobToFileLike(out, file);
    });
  }

  /**
   * Compress a media record before it's stored. Audio is passed through.
   */
  function prepareRecord(record) {
    if (!record) return Promise.resolve(record);
    var kind = String(record.kind || '').toLowerCase();
    if (kind === 'audio') return Promise.resolve(record);
    var file = record.file;
    if (!file || !isImageFile(file)) return Promise.resolve(record);
    return prepareIfImage(file).then(function (prepared) {
      if (prepared === file) return record;
      var nextRecord = Object.assign({}, record, {
        file: prepared,
        mime_type: (prepared && prepared.type) || record.mime_type || COMPRESSED_MIME
      });
      // Update file_size if the field is present
      if ('file_size' in record || prepared.size) {
        nextRecord.file_size = Number(prepared.size || 0);
      }
      return nextRecord;
    });
  }

  /**
   * Wrap KVLocalMedia.put so all images get compressed transparently.
   * Idempotent — only wraps once.
   */
  function installPutWrapper() {
    if (!window.KVLocalMedia || typeof window.KVLocalMedia.put !== 'function') return;
    if (window.KVLocalMedia.__imagePrepInstalled) return;
    var originalPut = window.KVLocalMedia.put;
    window.KVLocalMedia.put = function (record, options) {
      return prepareRecord(record).then(function (prepared) {
        return originalPut.call(window.KVLocalMedia, prepared, options);
      });
    };
    window.KVLocalMedia.__imagePrepInstalled = true;
  }

  // Public API
  window.KVImagePrep = {
    prepareIfImage: prepareIfImage,
    prepareRecord: prepareRecord,
    isImageFile: isImageFile,
    DEFAULT_MAX_DIMENSION: DEFAULT_MAX_DIMENSION,
    DEFAULT_QUALITY: DEFAULT_QUALITY
  };

  // Auto-install on load. Run multiple times to be safe (in case KVLocalMedia
  // is loaded after this file in a strange order).
  installPutWrapper();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installPutWrapper);
  } else {
    setTimeout(installPutWrapper, 50);
  }
})();
