/** Audited accessors for typed dictionaries with runtime-owned keys. */
export function getRecordValue<K extends PropertyKey, V>(
  record: Partial<Record<K, V>>,
  key: K,
): V | undefined {
  // eslint-disable-next-line security/detect-object-injection -- Generic key is constrained by the record's key type.
  return record[key];
}

export function setRecordValue<K extends PropertyKey, V>(
  record: Partial<Record<K, V>>,
  key: K,
  value: V,
): void {
  // eslint-disable-next-line security/detect-object-injection -- Generic key is constrained by the record's key type.
  record[key] = value;
}
