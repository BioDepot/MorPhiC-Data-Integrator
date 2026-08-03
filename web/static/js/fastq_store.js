// Persists user-selected FASTQ samples (including the File objects themselves)
// across page navigations. localStorage can only hold strings, so File/Blob
// data selected on the MorPhiC Data page has to live in IndexedDB instead;
// the Run Workflow page reads it back out when the form is actually submitted.
(function () {
  const DB_NAME = 'morphicdi_fastq';
  const DB_VERSION = 1;
  const STORE_NAME = 'samples';

  function openDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async function withStore(mode, fn) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, mode);
      const store = tx.objectStore(STORE_NAME);
      const result = fn(store);
      tx.oncomplete = () => resolve(result);
      tx.onerror = () => reject(tx.error);
    });
  }

  async function addSample(sample) {
    return new Promise(async (resolve, reject) => {
      try {
        const db = await openDB();
        const tx = db.transaction(STORE_NAME, 'readwrite');
        const store = tx.objectStore(STORE_NAME);
        const req = store.add(sample);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      } catch (err) { reject(err); }
    });
  }

  async function updateSample(id, patch) {
    return new Promise(async (resolve, reject) => {
      try {
        const db = await openDB();
        const tx = db.transaction(STORE_NAME, 'readwrite');
        const store = tx.objectStore(STORE_NAME);
        const getReq = store.get(id);
        getReq.onsuccess = () => {
          const existing = getReq.result || { id };
          const updated = Object.assign({}, existing, patch, { id });
          const putReq = store.put(updated);
          putReq.onsuccess = () => resolve(updated);
          putReq.onerror = () => reject(putReq.error);
        };
        getReq.onerror = () => reject(getReq.error);
      } catch (err) { reject(err); }
    });
  }

  async function deleteSample(id) {
    return withStore('readwrite', store => store.delete(id));
  }

  async function getAllSamples() {
    return new Promise(async (resolve, reject) => {
      try {
        const db = await openDB();
        const tx = db.transaction(STORE_NAME, 'readonly');
        const store = tx.objectStore(STORE_NAME);
        const req = store.getAll();
        req.onsuccess = () => resolve(req.result || []);
        req.onerror = () => reject(req.error);
      } catch (err) { reject(err); }
    });
  }

  async function clearAll() {
    return withStore('readwrite', store => store.clear());
  }

  window.FastqStore = { addSample, updateSample, deleteSample, getAllSamples, clearAll };
})();
