/**
 * Unit tests for CBMI utility functions.
 * Run with: node static/js/cbmi.test.js
 */
"use strict";

const assert = require("node:assert/strict");
const { computeCbmi, calculateBodyIndex, getConditionBand, getBreedParameters, DEFAULT_RATIO } = require("./cbmi.js");

/**
 * Helper for approximate numeric assertions.
 */
function assertApprox(actual, expected, delta, message) {
  assert.ok(Math.abs(actual - expected) <= delta, `${message}: expected ${expected} +/- ${delta}, got ${actual}`);
}

/**
 * Covers required expected result.
 */
function testBeagleExpectedOutcome() {
  const result = computeCbmi(12.8, 38, "beagle");
  assertApprox(result.cbmi, 56.7, 0.3, "Beagle CBMI");
  assert.equal(result.conditionBand, "Ideal");
  assert.equal(result.portionAdjustment, "Maintain");
}

function testBreedSpecificRatios() {
  const dachshund = computeCbmi(9, 22, "dachshund");
  const shepherd = computeCbmi(32, 60, "german_shepherd");
  assert.ok(dachshund.estimatedLengthCm > 35);
  assert.ok(shepherd.estimatedLengthCm > 70);
}

function testUnknownBreedFallback() {
  const params = getBreedParameters("mixed_breed");
  assert.equal(params.lengthHeightRatio, DEFAULT_RATIO);
  assert.equal(params.usesDefaultRatio, true);
  const result = computeCbmi(18, 45, "mixed_breed");
  assert.ok(Number.isFinite(result.cbmi));
}

function testBands() {
  assert.equal(getConditionBand(44.9).conditionBand, "Underweight");
  assert.equal(getConditionBand(45).conditionBand, "Ideal");
  assert.equal(getConditionBand(65).conditionBand, "Ideal");
  assert.equal(getConditionBand(72).conditionBand, "Overweight");
  assert.equal(getConditionBand(81).conditionBand, "Obese");
}

function testValidationErrors() {
  assert.throws(() => computeCbmi(0.4, 35, "beagle"), /Weight must be between/);
  assert.throws(() => computeCbmi(10, 9, "beagle"), /Height to shoulder must be between/);
}

function testFelineVerificationCases() {
  const beagle = calculateBodyIndex(12.8, 38, "beagle", "dog");
  const dachshund = calculateBodyIndex(9, 22, "dachshund", "dog");
  const persian = calculateBodyIndex(4.5, 23, "persian", "cat");
  const siamese = calculateBodyIndex(5.5, 21, "siamese", "cat");

  assertApprox(beagle.index, 56.7, 0.5, "Beagle index");
  assert.equal(beagle.band.label, "Ideal");
  assert.equal(dachshund.band.label, "Ideal");
  assertApprox(persian.index, 38.6, 0.5, "Persian index");
  assert.equal(persian.band.label, "Ideal");
  assert.equal(siamese.band.label, "Overweight");
}

function run() {
  testBeagleExpectedOutcome();
  testBreedSpecificRatios();
  testUnknownBreedFallback();
  testBands();
  testValidationErrors();
  testFelineVerificationCases();
  console.log("All CBMI unit tests passed.");
}

run();
