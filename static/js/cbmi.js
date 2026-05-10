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

  const DOG_GEOMETRY = Object.freeze({
    default: Object.freeze({ ratio: 1.30 }),
    shih_tzu: Object.freeze({ ratio: 1.35 }),
    chihuahua: Object.freeze({ ratio: 1.20 }),
    pomeranian: Object.freeze({ ratio: 1.25 }),
    beagle: Object.freeze({ ratio: 1.25 }),
    labrador_retriever: Object.freeze({ ratio: 1.15 }),
    golden_retriever: Object.freeze({ ratio: 1.15 }),
    german_shepherd: Object.freeze({ ratio: 1.20 }),
    siberian_husky: Object.freeze({ ratio: 1.18 }),
    poodle_toy: Object.freeze({ ratio: 1.22 }),
    poodle_miniature: Object.freeze({ ratio: 1.20 }),
    poodle_standard: Object.freeze({ ratio: 1.18 }),
    aspin_small: Object.freeze({ ratio: 1.28 }),
    aspin_medium: Object.freeze({ ratio: 1.30 }),
    aspin_large: Object.freeze({ ratio: 1.32 }),
    french_bulldog: Object.freeze({ ratio: 1.40 }),
    pug: Object.freeze({ ratio: 1.45 }),
    dachshund: Object.freeze({ ratio: 1.80 }),
    pembroke_welsh_corgi: Object.freeze({ ratio: 1.55 }),
    rottweiler: Object.freeze({ ratio: 1.18 }),
    american_pit_bull_terrier: Object.freeze({ ratio: 1.22 }),
    boxer: Object.freeze({ ratio: 1.20 }),
    doberman_pinscher: Object.freeze({ ratio: 1.17 }),
    dalmatian: Object.freeze({ ratio: 1.22 }),
    great_dane: Object.freeze({ ratio: 1.15 }),
    shiba_inu: Object.freeze({ ratio: 1.25 }),
    chow_chow: Object.freeze({ ratio: 1.30 }),
    cavalier_king_charles_spaniel: Object.freeze({ ratio: 1.28 }),
    yorkshire_terrier: Object.freeze({ ratio: 1.22 }),
    maltese: Object.freeze({ ratio: 1.25 }),
    english_bulldog: Object.freeze({ ratio: 1.45 }),
    border_collie: Object.freeze({ ratio: 1.18 }),
    australian_shepherd: Object.freeze({ ratio: 1.20 }),
  });

  const CAT_GEOMETRY = Object.freeze({
    default: Object.freeze({ ratio: 1.10 }),
    persian: Object.freeze({ ratio: 1.05 }),
    siamese: Object.freeze({ ratio: 1.15 }),
    maine_coon: Object.freeze({ ratio: 1.20 }),
    british_shorthair: Object.freeze({ ratio: 1.10 }),
    ragdoll: Object.freeze({ ratio: 1.18 }),
    bengal: Object.freeze({ ratio: 1.16 }),
    scottish_fold: Object.freeze({ ratio: 1.08 }),
    puspin_native: Object.freeze({ ratio: 1.10 }),
    american_shorthair: Object.freeze({ ratio: 1.12 }),
    russian_blue: Object.freeze({ ratio: 1.12 }),
    sphynx: Object.freeze({ ratio: 1.10 }),
    norwegian_forest: Object.freeze({ ratio: 1.22 }),
    exotic_shorthair: Object.freeze({ ratio: 1.08 }),
    burmese: Object.freeze({ ratio: 1.10 }),
    abyssinian: Object.freeze({ ratio: 1.15 }),
    oriental_shorthair: Object.freeze({ ratio: 1.15 }),
    turkish_angora: Object.freeze({ ratio: 1.14 }),
    tonkinese: Object.freeze({ ratio: 1.14 }),
  });

  const DOG_BANDS = Object.freeze([
    Object.freeze({ max: 45, label: "Underweight", portion: +0.10 }),
    Object.freeze({ max: 65, label: "Ideal", portion: 0.00 }),
    Object.freeze({ max: 80, label: "Overweight", portion: -0.10 }),
    Object.freeze({ max: Infinity, label: "Obese", portion: -0.20 }),
  ]);

  const CAT_BANDS = Object.freeze([
    Object.freeze({ max: 30, label: "Underweight", portion: +0.10 }),
    Object.freeze({ max: 45, label: "Ideal", portion: 0.00 }),
    Object.freeze({ max: 60, label: "Overweight", portion: -0.10 }),
    Object.freeze({ max: Infinity, label: "Obese", portion: -0.20 }),
  ]);

  const DOG_ID_ALIASES = Object.freeze({
    labrador: "labrador_retriever",
    poodle_mini: "poodle_miniature",
    poodle_std: "poodle_standard",
    corgi: "pembroke_welsh_corgi",
    pit_bull: "american_pit_bull_terrier",
    doberman: "doberman_pinscher",
    cavalier: "cavalier_king_charles_spaniel",
    bulldog: "english_bulldog",
  });

  const CAT_ID_ALIASES = Object.freeze({
    puspin: "puspin_native",
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
   * Species-aware body index using breed geometry and species bands.
   */
  function calculateBodyIndex(weightKg, heightCm, breedId, petType) {
    const type = petType === "cat" ? "cat" : "dog";
    const normalizedBreedId = String(breedId || "").trim().toLowerCase();
    const mappedBreedId = type === "cat"
      ? (CAT_ID_ALIASES[normalizedBreedId] || normalizedBreedId)
      : (DOG_ID_ALIASES[normalizedBreedId] || normalizedBreedId);
    const geometry = type === "cat" ? CAT_GEOMETRY : DOG_GEOMETRY;
    const bands = type === "cat" ? CAT_BANDS : DOG_BANDS;
    const ratio = (geometry[mappedBreedId] || geometry.default).ratio;
    const estimatedLengthCm = heightCm * ratio;
    const lengthM = estimatedLengthCm / 100;
    let index = weightKg / (lengthM * lengthM);
    if (type === "cat") {
      index = index / 2;
    }
    const roundedIndex = +index.toFixed(1);
    const band = bands.find((x) => roundedIndex <= x.max) || bands[bands.length - 1];

    return {
      index: roundedIndex,
      band,
      estLengthCm: Math.round(estimatedLengthCm),
      ratio,
    };
  }

  /**
   * Backward compatible feline entrypoint for existing integrations.
   */
  function computeFelineCbmi(weightKg, heightCm, breedId) {
    const result = calculateBodyIndex(weightKg, heightCm, breedId, "cat");
    return {
      cbmi: result.index,
      conditionBand: result.band.label,
      portionAdjustment: `${Math.round(result.band.portion * 100)}%`,
      estimatedLengthCm: result.estLengthCm,
      lengthHeightRatio: result.ratio,
      idealWeightMin: null,
      idealWeightMax: null,
      warning: "",
    };
  }

  const api = {
    DEFAULT_RATIO,
    BREED_PARAMETERS,
    DOG_GEOMETRY,
    CAT_GEOMETRY,
    DOG_BANDS,
    CAT_BANDS,
    getBreedParameters,
    getConditionBand,
    computeCbmi,
    computeFelineCbmi,
    calculateBodyIndex,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  globalScope.CBMI = api;
  globalScope.CBMI.computeFelineCbmi = computeFelineCbmi;
})(typeof globalThis !== "undefined" ? globalThis : window);
