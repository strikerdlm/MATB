/** Keep queued heavy work distinct from a completed scientific result. */
export async function stationFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const response = await fetch(input, init);
  const job = response.headers?.get("X-MATB-Station-Job");
  if (response.status === 202 && job) {
    throw new Error(
      `Work queued / Trabajo en cola: ${job}. Close the visit after collection / Cierre la visita al terminar. Status / Estado: /station`,
    );
  }
  return response;
}
