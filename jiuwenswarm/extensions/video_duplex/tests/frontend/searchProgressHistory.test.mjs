import assert from 'node:assert/strict';
import test from 'node:test';
import {
  MAX_SEARCH_PROGRESS_JOBS,
  mergeSearchProgressJob,
  searchProgressOptionLabel,
  selectSearchProgressJob,
} from '../../../../channels/web/frontend/node_modules/.cache/search-presentation/searchPresentation.js';

function payload(id, query, status = 'running', sequence = 1) {
  return {
    job_id: id,
    query,
    status,
    progress: {
      stage: 'search',
      title: `${query} step ${sequence}`,
      status,
      sequence,
    },
  };
}

test('mergeSearchProgressJob keeps creation order when an older job updates', () => {
  let jobs = mergeSearchProgressJob([], payload('first', 'first query'));
  jobs = mergeSearchProgressJob(jobs, payload('second', 'second query'));
  jobs = mergeSearchProgressJob(jobs, payload('first', 'first query', 'completed', 2));

  assert.deepEqual(jobs.map((job) => job.id), ['first', 'second']);
  assert.equal(jobs[0].status, 'completed');
  assert.equal(jobs[0].progress.length, 2);
});

test('mergeSearchProgressJob retains the latest bounded history', () => {
  let jobs = [];
  for (let index = 1; index <= MAX_SEARCH_PROGRESS_JOBS + 2; index += 1) {
    jobs = mergeSearchProgressJob(jobs, payload(`job-${index}`, `query ${index}`));
  }

  assert.equal(jobs.length, MAX_SEARCH_PROGRESS_JOBS);
  assert.equal(jobs[0].id, 'job-3');
  assert.equal(jobs.at(-1).id, `job-${MAX_SEARCH_PROGRESS_JOBS + 2}`);
});

test('selectSearchProgressJob supports pinned history and falls back to latest', () => {
  const jobs = [
    mergeSearchProgressJob([], payload('first', 'first query'))[0],
    mergeSearchProgressJob([], payload('second', 'second query'))[0],
  ];

  assert.equal(selectSearchProgressJob(jobs, 'first')?.id, 'first');
  assert.equal(selectSearchProgressJob(jobs, '')?.id, 'second');
  assert.equal(selectSearchProgressJob(jobs, 'expired')?.id, 'second');
});

test('searchProgressOptionLabel presents query and status without internal id', () => {
  const job = mergeSearchProgressJob([], payload('private-id', '香港今天的天气', 'completed'))[0];
  assert.equal(searchProgressOptionLabel(job, 3), '3. 香港今天的天气 (已完成)');
  assert.doesNotMatch(searchProgressOptionLabel(job, 3), /private-id/);
});

test('queued execution is labelled explicitly and late snapshots do not undo completion', () => {
  let jobs = mergeSearchProgressJob([], payload('one', 'request', 'queued'));
  assert.match(searchProgressOptionLabel(jobs[0], 1), /排队中/);
  jobs = mergeSearchProgressJob(jobs, payload('one', 'request', 'running', 2));
  jobs = mergeSearchProgressJob(jobs, payload('one', 'request', 'queued', 1));
  assert.equal(jobs[0].status, 'running');
  jobs = mergeSearchProgressJob(jobs, payload('one', 'request', 'completed', 3));
  jobs = mergeSearchProgressJob(jobs, payload('one', 'request', 'running', 2));
  assert.equal(jobs[0].status, 'completed');
});

test('subagent frames stay out of the progress list', () => {
  // They are shown in the 子智能体 panel; here each frame would add a row that never completes.
  const history = [
    { stage: 'search', title: 'search step', status: 'running', sequence: 1 },
    { stage: 'subagent', title: '子智能体：cua_agent', status: 'running', sequence: 2 },
    { stage: 'subagent', title: '子智能体：cua_agent', status: 'running', sequence: 3 },
    { stage: 'answer', title: 'answer', status: 'completed', sequence: 4 },
  ];
  const [job] = mergeSearchProgressJob([], { job_id: 'voice', query: 'q', status: 'completed', progress_history: history });
  assert.deepEqual(job.progress.map((entry) => entry.stage), ['search', 'answer']);
  assert.equal(job.status, 'completed');
});
