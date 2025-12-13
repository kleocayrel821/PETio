/**
 * Create Listing Page interactions
 * Handles: inline validation, counters, progress, dropzone preview, autosave, preview modal.
 * Accessible: maintains ARIA attributes and proper focus management.
 */
(function () {
  const qs = (sel, root = document) => root.querySelector(sel);
  const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function formatCurrency(value) {
    const num = Number(value);
    if (Number.isNaN(num)) return '₱0.00';
    return `₱${num.toFixed(2)}`;
  }

  function setFieldState(fieldEl, isValid, message) {
    const container = fieldEl.closest('.field');
    if (!container) return;
    container.classList.toggle('invalid', !isValid);
    container.classList.toggle('valid', !!isValid);
    fieldEl.setAttribute('aria-invalid', String(!isValid));
    if (message) {
      fieldEl.setAttribute('aria-describedby', `${fieldEl.id}-error`);
      let errLabel = qs(`#${fieldEl.id}-error`) || document.createElement('div');
      errLabel.id = `${fieldEl.id}-error`;
      errLabel.className = 'label label-text-alt text-error';
      errLabel.setAttribute('role', 'alert');
      errLabel.textContent = message;
      container.appendChild(errLabel);
    } else {
      const errLabel = qs(`#${fieldEl.id}-error`);
      if (errLabel) errLabel.remove();
      fieldEl.removeAttribute('aria-describedby');
    }
  }

  function updateProgress(progressEl, fields) {
    const total = fields.length;
    const completed = fields.reduce((acc, el) => acc + (el.value && el.value.toString().trim().length > 0 ? 1 : 0), 0);
    const value = Math.round((completed / total) * 100);
    if (progressEl) progressEl.value = value;
  }

  function setupCounters({ titleInput, titleCountEl, titleMaxEl, descInput, descCountEl }) {
    const updateTitle = () => {
      if (!titleInput || !titleCountEl || !titleMaxEl) return;
      const len = (titleInput.value || '').length;
      titleCountEl.textContent = String(len);
      const max = Number(titleMaxEl.textContent || 120);
      const ok = len > 0 && len <= max;
      setFieldState(titleInput, ok, ok ? '' : len === 0 ? 'Title is required' : `Max ${max} characters`);
    };
    const updateDesc = () => {
      if (!descInput || !descCountEl) return;
      const len = (descInput.value || '').length;
      descCountEl.textContent = String(len);
      setFieldState(descInput, len > 0, len > 0 ? '' : 'Description is required');
    };
    ['input', 'change'].forEach(evt => {
      titleInput && titleInput.addEventListener(evt, updateTitle);
      descInput && descInput.addEventListener(evt, updateDesc);
    });
    updateTitle();
    updateDesc();
  }

  function setupDropzone({ dropzoneEl, fileInput, previewImgEl, selectBtn }) {
    if (!dropzoneEl || !fileInput) return;

    const openFilePicker = () => fileInput.click();
    selectBtn && selectBtn.addEventListener('click', openFilePicker);
    dropzoneEl.addEventListener('click', openFilePicker);
    dropzoneEl.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openFilePicker(); } });

    const handleFiles = (files) => {
      if (!files || files.length === 0) return;
      const file = files[0];
      if (!file.type.startsWith('image/')) return;
      const reader = new FileReader();
      reader.onload = () => {
        if (previewImgEl) {
          previewImgEl.src = reader.result;
          previewImgEl.classList.remove('hidden');
        }
      };
      reader.readAsDataURL(file);
    };

    fileInput.addEventListener('change', (e) => handleFiles(e.target.files));
    dropzoneEl.addEventListener('dragover', (e) => { e.preventDefault(); dropzoneEl.classList.add('dragover'); });
    dropzoneEl.addEventListener('dragleave', () => dropzoneEl.classList.remove('dragover'));
    dropzoneEl.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzoneEl.classList.remove('dragover');
      const dt = e.dataTransfer;
      if (dt && dt.files && dt.files.length) {
        try {
          const transfer = new DataTransfer();
          Array.from(dt.files).forEach(f => transfer.items.add(f));
          fileInput.files = transfer.files;
        } catch (_) {
          try { fileInput.files = dt.files; } catch (_) { /* ignore */ }
        }
        handleFiles(fileInput.files || dt.files);
        fileInput.dispatchEvent(new Event('change'));
      }
    });
  }

  function setupPreview({ modalEl, titleInput, priceInput, quantityInput, categorySelect, descInput, previewTitleEl, previewPriceEl, previewStockEl, previewCategoryEl, previewDescEl, previewImgEl, previewPlaceholderEl, sourceImgEl }) {
    return () => {
      if (!modalEl) return;
      // Populate
      if (previewTitleEl) previewTitleEl.textContent = titleInput?.value || 'Untitled';
      if (previewPriceEl) previewPriceEl.textContent = formatCurrency(priceInput?.value || 0);
      if (previewStockEl) previewStockEl.textContent = `Stock: ${quantityInput?.value || '—'}`;
      if (previewCategoryEl) previewCategoryEl.textContent = categorySelect?.selectedOptions?.[0]?.text || 'Uncategorized';
      if (previewDescEl) previewDescEl.textContent = descInput?.value || 'No description provided.';
      if (sourceImgEl && sourceImgEl.src && previewImgEl) {
        previewImgEl.src = sourceImgEl.src;
      }
      if (previewImgEl && previewImgEl.src) {
        previewImgEl.classList.remove('hidden');
        previewPlaceholderEl?.classList.add('hidden');
      } else {
        previewImgEl?.classList.add('hidden');
        previewPlaceholderEl?.classList.remove('hidden');
      }
      // Show modal
      if (typeof modalEl.showModal === 'function') modalEl.showModal();
      else modalEl.setAttribute('open', 'true');
      // Focus for accessibility
      modalEl.querySelector('button.btn')?.focus();
    };
  }

  function setupAutosave({ formEl, inputs, indicatorEl, timeEl, restoreBtn, clearBtn }) {
    const key = 'createListingDraft';
    let saveTimer = null;
    const saveDraft = () => {
      const payload = {};
      inputs.forEach(el => { if (el?.id) payload[el.id] = el.value; });
      try {
        localStorage.setItem(key, JSON.stringify(payload));
        const stamp = new Date();
        if (indicatorEl) indicatorEl.innerHTML = `<i class="fas fa-save mr-1"></i> Draft saved`;
        if (timeEl) timeEl.textContent = `@ ${stamp.toLocaleTimeString()}`;
      } catch (e) { /* ignore */ }
    };
    const scheduleSave = () => {
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(saveDraft, 600);
    };
    inputs.forEach(el => ['input', 'change'].forEach(evt => el && el.addEventListener(evt, scheduleSave)));

    restoreBtn && restoreBtn.addEventListener('click', () => {
      try {
        const raw = localStorage.getItem(key);
        if (!raw) return;
        const payload = JSON.parse(raw);
        inputs.forEach(el => { if (el?.id && payload[el.id] !== undefined) el.value = payload[el.id]; });
        // Trigger input events to refresh counters/validation
        inputs.forEach(el => el && el.dispatchEvent(new Event('input')));
      } catch (e) { /* ignore */ }
    });

    clearBtn && clearBtn.addEventListener('click', () => {
      localStorage.removeItem(key);
      if (indicatorEl) indicatorEl.innerHTML = `<i class="fas fa-save mr-1"></i> Draft cleared`;
      if (timeEl) timeEl.textContent = '';
    });
  }

  function setupValidation({ formEl, submitBtn }) {
    if (!formEl) return;
    formEl.addEventListener('submit', (e) => {
      const requiredEls = qsa('input[required], select[required], textarea[required]', formEl);
      let ok = true;
      requiredEls.forEach(el => {
        const valid = !!(el.value && String(el.value).trim().length);
        setFieldState(el, valid, valid ? '' : 'This field is required');
        if (!valid) ok = false;
      });
      if (!ok) {
        e.preventDefault();
        const firstInvalid = requiredEls.find(el => el.getAttribute('aria-invalid') === 'true');
        firstInvalid?.focus();
        return;
      }
      // Loading state
      if (submitBtn) submitBtn.setAttribute('aria-busy', 'true');
    });
  }

  window.CreateListingPage = {
    /**
     * Initialize the page with provided selectors.
     * @param {Object} cfg
     */
    init(cfg) {
      const s = cfg?.selectors || {};
      const formEl = qs(s.form);
      const titleInput = qs(s.title);
      const priceInput = qs(s.price);
      const quantityInput = qs(s.quantity);
      const categorySelect = qs(s.category);
      const descInput = qs(s.description);
      const fileInput = qs(s.mainImageInput);
      const dropzoneEl = qs(s.imageDropzone);
      const previewImgEl = qs(s.imagePreview);
      const selectBtn = qs(s.imageSelectBtn);
      const progressEl = qs(s.progress);
      const titleCountEl = qs(s.titleCount);
      const titleMaxEl = qs(s.titleMax);
      const descCountEl = qs(s.descCount);
      const autosaveIndicator = qs(s.autosaveIndicator);
      const autosaveTime = qs(s.autosaveTime);
      const restoreDraftBtn = qs(s.restoreDraftBtn);
      const clearDraftBtn = qs(s.clearDraftBtn);
      const previewBtn = qs(s.previewBtn);
      const submitBtn = qs(s.submitBtn);
      const previewModal = qs(s.previewModal);
      const previewTitleEl = qs(s.previewTitle);
      const previewCategoryEl = qs(s.previewCategory);
      const previewPriceEl = qs(s.previewPrice);
      const previewStockEl = qs(s.previewStock);
      const previewDescEl = qs(s.previewDescription);
      const previewModalImg = qs(s.previewImage);
      const previewPlaceholderEl = qs(s.previewPlaceholder);

      // Progress updates
      const progressFields = [titleInput, priceInput, quantityInput, categorySelect, descInput];
      progressFields.forEach(el => ['input', 'change'].forEach(evt => el && el.addEventListener(evt, () => updateProgress(progressEl, progressFields))));
      updateProgress(progressEl, progressFields);

      setupCounters({ titleInput, titleCountEl, titleMaxEl, descInput, descCountEl });
      setupDropzone({ dropzoneEl, fileInput, previewImgEl, selectBtn });
      setupAutosave({ formEl, inputs: progressFields.filter(Boolean), indicatorEl: autosaveIndicator, timeEl: autosaveTime, restoreBtn: restoreDraftBtn, clearBtn: clearDraftBtn });
      setupValidation({ formEl, submitBtn });

      const applyPreview = setupPreview({
        modalEl: previewModal,
        titleInput,
        priceInput,
        quantityInput,
        categorySelect,
        descInput,
        previewTitleEl,
        previewPriceEl,
        previewStockEl,
        previewCategoryEl,
        previewDescEl,
        previewImgEl: previewModalImg,
        previewPlaceholderEl,
        sourceImgEl: previewImgEl,
      });
      previewBtn && previewBtn.addEventListener('click', applyPreview);
    }
  };
})();
