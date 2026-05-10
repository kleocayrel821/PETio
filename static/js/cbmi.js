/**
 * Breed-aware Canine Body Mass Index (CBMI) utilities.
 * This module avoids the invalid dog formula `weight / shoulder_height^2`
 * by first estimating body length from breed geometry.
 */
(function (globalScope) {
  "use strict";

  const DEFAULT_RATIO = 1.30;

  /**
   * Authoritative breed parameters.
   * `lengthHeightRatio` is used to estimate body length from shoulder height.
   */
  const BREED_PARAMETERS = Object.freeze({
    beagle: Object.freeze({ lengthHeightRatio: 1.25, idealWeightMin: 9, idealWeightMax: 11 }),
    labrador_retriever: Object.freeze({ lengthHeightRatio: 1.15, idealWeightMin: 25, idealWeightMax: 36 }),
    german_shepherd: Object.freeze({ lengthHeightRatio: 1.20, idealWeightMin: 22, idealWeightMax: 40 }),
    dachshund: Object.freeze({ lengthHeightRatio: 1.80, idealWeightMin: 7, idealWeightMax: 15 }),
    shih_tzu: Object.freeze({ lengthHeightRatio: 1.35, idealWeightMin: 4, idealWeightMax: 7.5 }),
  });

  const BREED_ALIASES = Object.freeze({
    labrador: "labrador_retriever",
  });

  const FELINE_MODEL = Object.freeze({
    default: Object.freeze({ lengthHeightRatio: 1.10 }),
    breeds: Object.freeze({
      persian: Object.freeze({ ratio: 1.05, idealMin: 3.5, idealMax: 5.5 }),
      siamese: Object.freeze({ ratio: 1.15, idealMin: 2.5, idealMax: 5.5 }),
      maine_coon: Object.freeze({ ratio: 1.20, idealMin: 5.5, idealMax: 8.5 }),
      british_shorthair: Object.freeze({ ratio: 1.10, idealMin: 4, idealMax: 8 }),
      ragdoll: Object.freeze({ ratio: 1.18, idealMin: 4.5, idealMax: 9 }),
      bengal: Object.freeze({ ratio: 1.16, idealMin: 4.5, idealMax: 7 }),
      scottish_fold: Object.freeze({ ratio: 1.08, idealMin: 2.7, idealMax: 6 }),
      puspin: Object.freeze({ ratio: 1.10, idealMin: 3, idealMax: 5 }),
      american_shorthair: Object.freeze({ ratio: 1.12, idealMin: 3, idealMax: 5.5 }),
      russian_blue: Object.freeze({ ratio: 1.12, idealMin: 3, idealMax: 5.5 }),
      sphynx: Object.freeze({ ratio: 1.10, idealMin: 3, idealMax: 5.5 }),
      norwegian_forest: Object.freeze({ ratio: 1.22, idealMin: 4.5, idealMax: 9 }),
      exotic_shorthair: Object.freeze({ ratio: 1.08, idealMin: 3, idealMax: 6 }),
      burmese: Object.freeze({ ratio: 1.10, idealMin: 3, idealMax: 5 }),
      abyssinian: Object.freeze({ ratio: 1.15, idealMin: 2.5, idealMax: 4.5 }),
      oriental_shorthair: Object.freeze({ ratio: 1.15, idealMin: 3, idealMax: 4.5 }),
      turkish_angora: Object.freeze({ ratio: 1.14, idealMin: 3, idealMax: 5.5 }),
      tonkinese: Object.freeze({ ratio: 1.14, idealMin: 3, idealMax: 5.5 }),
    }),
    bands: Object.freeze([
      Object.freeze({ max: 30, label: "Underweight", portion: "+10%" }),
      Object.freeze({ max: 45, label: "Ideal", portion: "0%" }),
      Object.freeze({ max: 60, label: "Overweight", portion: "-10%" }),
      Object.freeze({ max: 999, label: "Obese", portion: "-20%" }),
    ]),
  });

  /**
   * Maps a CBMI value to condition and feeding adjustment.
   */
  function getConditionBand(cbmi) {
    if (cbmi < 45) {
      return { conditionBand: "Underweight", portionAdjustment: "+10%" };
    }
    if (cbmi <= 65) {
      return { conditionBand: "Ideal", portionAdjustment: "Maintain" };
    }
    if (cbmi <= 80) {
      return { conditionBand: "Overweight", portionAdjustment: "-10%" };
    }
    return { conditionBand: "Obese", portionAdjustment: "-20%" };
  }

  /**
   * Normalizes breed IDs for table lookup.
   */
  function normalizeBreedId(breedId) {
    const key = String(breedId || "").trim().toLowerCase();
    return BREED_ALIASES[key] || key;
  }

  /**
   * Resolves breed parameters with fallback ratio for unknown/mixed breeds.
   */
  function getBreedParameters(breedId) {
    const normalizedId = normalizeBreedId(breedId);
    const found = BREED_PARAMETERS[normalizedId];
    if (found) {
      return { breedId: normalizedId, ...found, usesDefaultRatio: false };
    }
    return {
      breedId: normalizedId || "mixed_or_unknown",
      lengthHeightRatio: DEFAULT_RATIO,
      idealWeightMin: null,
      idealWeightMax: null,
      usesDefaultRatio: true,
    };
  }

  /**
   * Builds a warning when weight is far from breed ideal.
   */
  function getBreedWeightWarning(weightKg, breedParams) {
    if (!Number.isFinite(breedParams.idealWeightMin) || !Number.isFinite(breedParams.idealWeightMax)) {
      return null;
    }
    const lowerWarn = breedParams.idealWeightMin * 0.75;
    const upperWarn = breedParams.idealWeightMax * 1.25;
    if (weightKg < lowerWarn || weightKg > upperWarn) {
      return `Weight is far outside the breed ideal range (${breedParams.idealWeightMin}-${breedParams.idealWeightMax} kg).`;
    }
    return null;
  }

  /**
   * Pure CBMI computation.
   * Why this model:
   * - Shoulder height alone is not a valid body-size proxy for quadrupeds.
   * - Body length is estimated from breed geometry, then squared in the index denominator.
   */
  function computeCbmi(weightKg, heightCm, breedId) {
    if (!Number.isFinite(weightKg) || weightKg < 0.5 || weightKg > 120) {
      throw new Error("Weight must be between 0.5 kg and 120 kg.");
    }
    if (!Number.isFinite(heightCm) || heightCm < 10 || heightCm > 110) {
      throw new Error("Height to shoulder must be between 10 cm and 110 cm.");
    }

    const breed = getBreedParameters(breedId);
    const estimatedLengthCm = heightCm * breed.lengthHeightRatio;
    const estimatedLengthM = estimatedLengthCm / 100;
    const cbmiRaw = weightKg / (estimatedLengthM * estimatedLengthM);
    const cbmi = Number(cbmiRaw.toFixed(1));
    const mapped = getConditionBand(cbmi);
    const warning = getBreedWeightWarning(weightKg, breed);

    return {
      cbmi,
      conditionBand: mapped.conditionBand,
      portionAdjustment: mapped.portionAdjustment,
      estimatedLengthCm: Number(estimatedLengthCm.toFixed(1)),
      lengthHeightRatio: breed.lengthHeightRatio,
      idealWeightMin: breed.idealWeightMin,
      idealWeightMax: breed.idealWeightMax,
      usesDefaultRatio: breed.usesDefaultRatio,
      warning,
    };
  }

  /**
   * Feline CBMI based on cat-specific body geometry.
   */
  function computeFelineCbmi(weightKg, heightCm, breedId) {
    const b = FELINE_MODEL.breeds[breedId] || {};
    const ratio = b.ratio || FELINE_MODEL.default.lengthHeightRatio;

    const estimatedLengthCm = heightCm * ratio;
    const lengthM = estimatedLengthCm / 100;
    // Cat calibration coefficient keeps feline CBMI bands aligned with expected clinical ranges.
    const felineNormalization = 2;
    const cbmi = +(weightKg / (lengthM * lengthM * felineNormalization)).toFixed(1);

    const band = FELINE_MODEL.bands.find((x) => cbmi <= x.max);

    let warning = "";
    if (b.idealMin && (weightKg < b.idealMin || weightKg > b.idealMax)) {
      warning = "Weight is outside typical breed range.";
    }

    return {
      cbmi,
      conditionBand: band.label,
      portionAdjustment: band.portion,
      estimatedLengthCm: Math.round(estimatedLengthCm),
      lengthHeightRatio: ratio,
      idealWeightMin: b.idealMin ?? null,
      idealWeightMax: b.idealMax ?? null,
      warning,
    };
  }

  const api = {
    DEFAULT_RATIO,
    BREED_PARAMETERS,
    FELINE_MODEL,
    getBreedParameters,
    getConditionBand,
    computeCbmi,
    computeFelineCbmi,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  globalScope.CBMI = api;
  globalScope.CBMI.computeFelineCbmi = computeFelineCbmi;
})(typeof globalThis !== "undefined" ? globalThis : window);
