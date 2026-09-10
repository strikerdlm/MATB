import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StudyEditor } from "./StudyEditor";
vi.mock("@/lib/study", () => ({
  studyVersions: vi.fn(async () => ({ versions: [], active_version_id: null })),
  studyCall: vi.fn(async (path: string) =>
    path === "/drafts"
      ? []
      : path === "/bindings"
        ? { pvt: [{ binding_id: "pvt-browser-v1" }] }
        : {
            study: {
              study_id: "test-study",
              title: "Draft",
              synthetic: true,
              arms: ["A"],
              visits: [{ ordinal: 1, code: "T0", scheduled_day: 0 }],
              occasions: [
                {
                  key: "pre",
                  visit_ordinal: 1,
                  instrument: "pvt",
                  phase: "pre",
                  order: 1,
                  locale: "en",
                  condition_by_arm: { A: "rest" },
                  config: {},
                  prerequisite_keys: [],
                },
              ],
              recovery_intervals: [],
              rules: { preparation: "", repeat: "", interruption: "" },
            },
            analysis: {
              unit: "participant",
              outcomes: [
                {
                  key: "primary",
                  metric: "pvt.median_rt_ms",
                  occasion_keys: ["pre"],
                  summary: "individual",
                },
              ],
              contrasts: [],
              rules: {
                exclusions: "",
                denominators: "",
                qualification: "",
                pooling: "",
                historical_unknowns: "exclude",
              },
            },
          },
  ),
}));
describe("constrained authoring", () => {
  it("exposes occasion and required authored rule controls without JSON-only editing", async () => {
    render(<StudyEditor />);
    fireEvent.click(
      screen.getByRole("button", { name: /Load template|Cargar plantilla/ }),
    );
    await waitFor(() =>
      expect(
        screen.getByLabelText(/Preparation rule|Regla de preparación/),
      ).toBeTruthy(),
    );
    expect(screen.getByLabelText(/Instrument|Instrumento/)).toBeTruthy();
    expect(
      screen.getByLabelText(/Named researcher|Investigador responsable/),
    ).toBeTruthy();
    expect(
      screen
        .getByRole("button", { name: /Freeze|Congelar/ })
        .hasAttribute("disabled"),
    ).toBe(true);
  });
});

it("binds approval to the saved rehearsal hash and invalidates it when a form field changes", async () => {
  const api = await import("@/lib/study");
  const template = await api.studyCall("/templates/pre-post-recovery");
  vi.mocked(api.studyCall).mockImplementation(async (path, body) => {
    if (path === "/drafts" && body === undefined) return [] as never;
    if (path.endsWith("/history"))
      return { validations: [], rehearsals: [], approval: null } as never;
    if (path === "/bindings")
      return { pvt: [{ binding_id: "pvt-browser-v1" }] } as never;
    if (path.startsWith("/templates"))
      return structuredClone(template) as never;
    if (path.endsWith("/rehearse")) return { id: "rehearsal-current" } as never;
    if (path === "/drafts" || path === "/drafts/draft-current")
      return {
        id: "draft-current",
        sha256: "saved-hash",
        payload_json: JSON.stringify(body),
        frozen_version_id: null,
      } as never;
    return {} as never;
  });
  render(<StudyEditor />);
  fireEvent.click(
    screen.getByRole("button", { name: /Load template|Cargar plantilla/ }),
  );
  await screen.findByLabelText(
    /This draft is synthetic|Este borrador es sintético/,
  );
  fireEvent.click(
    screen.getByLabelText(/This draft is synthetic|Este borrador es sintético/),
  );
  fireEvent.change(
    screen.getByLabelText(/Named researcher|Investigador responsable/),
    { target: { value: "Dr Author" } },
  );
  fireEvent.change(
    screen.getByLabelText(/Reason and review|Motivo y declaración/),
    { target: { value: "Reviewed authored criteria" } },
  );
  fireEvent.click(screen.getByRole("button", { name: /^Rehearse$|^Ensayar$/ }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: /Freeze|Congelar/ }),
    ).toBeEnabled(),
  );
  fireEvent.change(screen.getByLabelText(/^Title$|^Título$/), {
    target: { value: "Amended title" },
  });
  expect(
    screen.getByRole("button", { name: /Freeze|Congelar/ }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: /^Rehearse$|^Ensayar$/ }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: /Freeze|Congelar/ }),
    ).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: /Freeze|Congelar/ }));
  await waitFor(() =>
    expect(api.studyCall).toHaveBeenCalledWith("/drafts/draft-current/freeze", {
      sha256: "saved-hash",
      rehearsal_id: "rehearsal-current",
      actor: "Dr Author",
      reason: "Reviewed authored criteria",
    }),
  );
});

it("reopens the same saved draft after leaving and edits before rehearsing/freezing", async () => {
  const api = await import("@/lib/study");
  const payload = await api.studyCall("/templates/pre-post-recovery");
  let saved = {
    id: "reopen-id",
    sha256: "hash-1",
    payload_json: JSON.stringify(payload),
    frozen_version_id: null,
  };
  vi.mocked(api.studyCall).mockImplementation(async (path, body) => {
    if (path === "/bindings") return { pvt: [] } as never;
    if (path === "/drafts" && body === undefined) return [saved] as never;
    if (path.endsWith("/history"))
      return { validations: [], rehearsals: [], approval: null } as never;
    if (path === "/drafts/reopen-id" && body === undefined)
      return saved as never;
    if (path === "/drafts/reopen-id" && body) {
      saved = {
        ...saved,
        payload_json: JSON.stringify(body),
        sha256: "hash-edited",
      };
      return saved as never;
    }
    if (path.endsWith("/rehearse")) return { id: "r-reopened" } as never;
    return {} as never;
  });
  const first = render(<StudyEditor />);
  fireEvent.change(
    await screen.findByLabelText(/Saved draft|Borrador guardado/),
    { target: { value: "reopen-id" } },
  );
  fireEvent.click(
    screen.getByRole("button", { name: /Open saved draft|Abrir borrador/ }),
  );
  await screen.findByLabelText(/^Title$|^Título$/);
  fireEvent.click(
    screen.getByRole("button", { name: /Save draft|Guardar borrador/ }),
  );
  await waitFor(() =>
    expect(api.studyCall).toHaveBeenCalledWith(
      "/drafts/reopen-id",
      expect.anything(),
      "PUT",
    ),
  );
  first.unmount();
  render(<StudyEditor />);
  fireEvent.change(
    await screen.findByLabelText(/Saved draft|Borrador guardado/),
    { target: { value: "reopen-id" } },
  );
  fireEvent.click(
    screen.getByRole("button", { name: /Open saved draft|Abrir borrador/ }),
  );
  fireEvent.change(await screen.findByLabelText(/^Title$|^Título$/), {
    target: { value: "Resumed draft" },
  });
  const synthetic = screen.getByLabelText(
    /This draft is synthetic|Este borrador es sintético/,
  );
  if ((synthetic as HTMLInputElement).checked) fireEvent.click(synthetic);
  fireEvent.change(
    screen.getByLabelText(/Named researcher|Investigador responsable/),
    { target: { value: "Dr Author" } },
  );
  fireEvent.change(
    screen.getByLabelText(/Reason and review|Motivo y declaración/),
    { target: { value: "Reviewed resumed draft" } },
  );
  fireEvent.click(screen.getByRole("button", { name: /^Rehearse$|^Ensayar$/ }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: /Freeze|Congelar/ }),
    ).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: /Freeze|Congelar/ }));
  await waitFor(() =>
    expect(api.studyCall).toHaveBeenCalledWith(
      "/drafts/reopen-id/freeze",
      expect.objectContaining({
        sha256: "hash-edited",
        rehearsal_id: "r-reopened",
      }),
    ),
  );
});

it('clears draft A history when a template or cloned version changes the content source', async () => {
  const api = await import('@/lib/study');
  const payload = {study:{study_id:'history-fixture',title:'History fixture',synthetic:true,arms:['A'],visits:[],occasions:[],enabled_instruments:[],recovery_intervals:[],rules:{preparation:'',repeat:'',interruption:''}},analysis:{unit:'participant',outcomes:[],contrasts:[],rules:{exclusions:'',denominators:'',qualification:'',pooling:'',historical_unknowns:'exclude'}}};
  const a = {id:'draft-a',sha256:'a',payload_json:JSON.stringify(payload),frozen_version_id:null};
  const b = {...a,id:'draft-b',sha256:'b'};
  vi.mocked(api.studyVersions).mockResolvedValue({active_version_id:null,versions:[{id:'version-b',...payload}]} as never);
  vi.mocked(api.studyCall).mockImplementation(async (path, body) => {
    if (path === '/bindings') return {} as never;
    if (path === '/drafts' && body === undefined) return [a] as never;
    if (path === '/drafts/draft-a') return a as never;
    if (path === '/drafts/draft-a/history') return {validations:[{draft_id:'draft-a',marker:'ONLY_A_HISTORY'}]} as never;
    if (path.startsWith('/templates')) return structuredClone(payload) as never;
    return b as never;
  });
  render(<StudyEditor/>);
  fireEvent.change(await screen.findByLabelText(/Saved draft|Borrador guardado/),{target:{value:'draft-a'}});
  fireEvent.click(screen.getByRole('button',{name:/Open saved draft|Abrir borrador/}));
  await screen.findByText(/ONLY_A_HISTORY/);
  fireEvent.click(screen.getByRole('button',{name:/Load template|Cargar plantilla/}));
  await waitFor(()=>expect(screen.queryByText(/ONLY_A_HISTORY/)).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole('button',{name:/Save draft|Guardar borrador/}));
  await screen.findByText(/Draft identity.*draft-b|Identidad del borrador.*draft-b/);
  expect(screen.queryByText(/ONLY_A_HISTORY/)).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/Saved draft|Borrador guardado/),{target:{value:'draft-a'}});
  fireEvent.click(screen.getByRole('button',{name:/Open saved draft|Abrir borrador/}));
  await screen.findByText(/ONLY_A_HISTORY/);
  fireEvent.click(screen.getByRole('button',{name:/Author amendment|Crear enmienda/}));
  await waitFor(()=>expect(screen.queryByText(/ONLY_A_HISTORY/)).not.toBeInTheDocument());
});
