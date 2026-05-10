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

  const api = Object.freeze({
    DEFAULT_RATIO,
    BREED_PARAMETERS,
    getBreedParameters,
    getConditionBand,
    computeCbmi,
  });

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  globalScope.CBMI = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
