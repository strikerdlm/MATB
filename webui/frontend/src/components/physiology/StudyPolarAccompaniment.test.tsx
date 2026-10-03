import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { StudyPolarAccompaniment } from './StudyPolarAccompaniment';
import { assignmentDetail, type AssignmentDetail, type StudyOccasion } from '@/lib/study';
import { getPolarCapture } from '@/lib/physiology/api';
import { createAttempt } from '@/lib/assessments';
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
vi.mock('@/lib/study', () => ({ assignmentDetail: vi.fn(), studyCall: vi.fn() }));
vi.mock('@/lib/physiology/api', () => ({ getPolarCapture: vi.fn() }));
vi.mock('@/lib/assessments', () => ({ createAttempt: vi.fn() }));
const companion = { key: 'block1_polar', accompanying_key: 'block1', prerequisite_keys: [] } as unknown as StudyOccasion;
const detail = { assignment: { id: 'assignment1', participant_id: 'P01' }, occasions: { block1_polar: 'occasion-polar' },
  attempts: { block1: [{ sources: [{ source_table: 'openmatb_suite_session', source_id: 'native1' }] }],
    block1_polar: [{ sources: [{ source_table: 'polar_capture', source_id: 'polar1' }] }] } } as unknown as AssignmentDetail;
beforeEach(() => { vi.resetAllMocks(); vi.mocked(assignmentDetail).mockResolvedValue(detail); });
it.each(['native1', 'wrong-session'])('admits only a recording paired to the exact native session: %s', async session => {
  vi.mocked(getPolarCapture).mockResolvedValue({ lifecycle: 'capturing', participant_pseudonym: 'P01', matb_session_id: session } as never);
  const ready = vi.fn();
  render(<StudyPolarAccompaniment detail={detail} companion={companion} onReady={ready} copy={(_es, en) => en} />);
  await waitFor(() => expect(ready).toHaveBeenCalledWith({ key: 'block1_polar', ready: session === 'native1' }));
});
it('opens only this assigned companion and preserves study purpose', async () => {
  vi.mocked(assignmentDetail).mockResolvedValue({ ...detail, attempts: { ...detail.attempts, block1_polar: [] } });
  vi.mocked(createAttempt).mockResolvedValue({ id: 'attempt-polar', acquisition_state: 'created' } as never);
  render(<StudyPolarAccompaniment detail={detail} companion={companion} onReady={vi.fn()} copy={(_es, en) => en} />);
  fireEvent.click(screen.getByRole('button', { name: 'Open block Polar recording' }));
  await waitFor(() => expect(push).toHaveBeenCalledWith('/physiology/polar-h10?purpose=study&attempt=attempt-polar'));
  expect(createAttempt).toHaveBeenCalledWith('occasion-polar', 'study');
});
