import { useCallback, useEffect, useRef, useState } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import { Button } from '../components/Button';
import {
  PipelineApiError,
  compactCacheLogs,
  fetchCacheEntries,
  fetchCacheFiles,
  fetchPipelineToken,
  rebuildCacheOutput,
  setProblemStatus,
  subscribePipelineEvents,
  updateCacheEntry,
  type CacheEntriesPage,
  type CacheEntry,
  type CacheFileSummary,
} from '../lib/pipeline';

const PAGE_SIZE = 200;

type RowState = { dirty: boolean; saving: boolean; saved: boolean; error: string };

export function TranslationEditorPage() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [projectDir, setProjectDir] = useState('');
  const [files, setFiles] = useState<CacheFileSummary[]>([]);
  const [activeFile, setActiveFile] = useState('');
  const [editable, setEditable] = useState(true);
  const [page, setPage] = useState<CacheEntriesPage | null>(null);
  const [filter, setFilter] = useState<{ q: string; locked: boolean; problem: boolean; untranslated: boolean }>({
    q: '',
    locked: false,
    problem: false,
    untranslated: false,
  });
  const [rows, setRows] = useState<Record<number, CacheEntry>>({});
  const [rowState, setRowState] = useState<Record<number, RowState>>({});
  const [jobLog, setJobLog] = useState<string[]>([]);
  const [jobRunning, setJobRunning] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await fetchPipelineToken();
        if (!cancelled) setReady(true);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshFiles = useCallback(async (dir: string) => {
    try {
      const data = await fetchCacheFiles(dir);
      setFiles(data.files);
      setEditable(data.editable);
      return data.files;
    } catch (err) {
      setError(err instanceof PipelineApiError ? `${err.code}: ${err.message}` : String(err));
      return [];
    }
  }, []);

  const loadPage = useCallback(
    async (dir: string, file: string, f: typeof filter, pageNum = 1) => {
      if (!dir || !file) return;
      try {
        const data = await fetchCacheEntries(dir, file, {
          q: f.q || undefined,
          locked: f.locked ? true : undefined,
          problem: f.problem ? true : undefined,
          untranslated: f.untranslated ? true : undefined,
          page: pageNum,
          page_size: PAGE_SIZE,
        });
        setPage(data);
        setRows(Object.fromEntries(data.entries.map((entry) => [entry.index, entry])));
        setRowState({});
      } catch (err) {
        setRowState({});
        setPage(null);
        setError(
          err instanceof PipelineApiError
            ? `[${err.code}] ${err.message}`
            : String(err),
        );
      }
    },
    [],
  );

  const loadProject = useCallback(
    async (dir: string) => {
      setProjectDir(dir);
      setError('');
      const list = await refreshFiles(dir);
      if (list.length > 0) {
        setActiveFile(list[0].name);
        void loadPage(dir, list[0].name, filter);
      } else {
        setActiveFile('');
        setPage(null);
      }
    },
    [refreshFiles, loadPage, filter],
  );

  const handleBrowseProject = useCallback(async () => {
    const selected = await open({ directory: true });
    if (typeof selected !== 'string') return;
    void loadProject(selected);
  }, [loadProject]);

  const handlePickFile = useCallback(
    (name: string) => {
      setActiveFile(name);
      void loadPage(projectDir, name, filter);
    },
    [projectDir, loadPage, filter],
  );

  const handleFilterChange = useCallback(
    (patch: Partial<typeof filter>) => {
      const next = { ...filter, ...patch };
      setFilter(next);
      setPage(null);
      void loadPage(projectDir, activeFile, next);
    },
    [filter, projectDir, activeFile, loadPage],
  );

  const saveRow = useCallback(
    async (entry: CacheEntry, patch: { pre_dst?: string; locked?: boolean }) => {
      setRowState((prev) => ({
        ...prev,
        [entry.index]: { dirty: false, saving: true, saved: false, error: '' },
      }));
      try {
        await updateCacheEntry({
          project: projectDir,
          file: activeFile,
          index: entry.index,
          pre_src: entry.pre_src,
          ...patch,
        });
        setRows((prev) => ({
          ...prev,
          [entry.index]: { ...prev[entry.index], ...patch } as CacheEntry,
        }));
        setRowState((prev) => ({
          ...prev,
          [entry.index]: { dirty: false, saving: false, saved: true, error: '' },
        }));
      } catch (err) {
        setRowState((prev) => ({
          ...prev,
          [entry.index]: {
            dirty: true,
            saving: false,
            saved: false,
            error: err instanceof PipelineApiError ? `${err.code}: ${err.message}` : String(err),
          },
        }));
      }
    },
    [projectDir, activeFile],
  );

  // SSE:重建输出等后台任务的事件流
  useEffect(() => {
    if (!ready) return () => undefined;
    return subscribePipelineEvents(
      (event) => {
        if (event.event === 'log') {
          setJobLog((prev) => [...prev.slice(-50), `[${event.data.step}] ${event.data.message}`]);
        } else if (event.event === 'job_started') {
          setJobRunning(true);
        } else if (event.event === 'job_done') {
          setJobRunning(false);
          setJobLog((prev) => [...prev, '完成 ✓']);
          void refreshFiles(projectDir);
        } else if (event.event === 'job_failed') {
          setJobRunning(false);
          setJobLog((prev) => [
            ...prev,
            `失败 [${event.data.code}] ${event.data.message.split('\n')[0]}`,
          ]);
        }
      },
      (message) => setJobLog((prev) => [...prev, `[连接] ${message}`]),
    );
  }, [ready, projectDir, refreshFiles]);

  const cycleProblemStatus = useCallback(
    async (entry: CacheEntry) => {
      const next =
        entry.problem_status === ''
          ? 'confirmed'
          : entry.problem_status === 'confirmed'
            ? 'ignored'
            : '';
      try {
        await setProblemStatus({
          project: projectDir,
          file: activeFile,
          index: entry.index,
          status: next,
        });
        setRows((prev) => ({
          ...prev,
          [entry.index]: { ...prev[entry.index], problem_status: next } as CacheEntry,
        }));
      } catch (err) {
        setError(
          err instanceof PipelineApiError ? `${err.code}: ${err.message}` : String(err),
        );
      }
    },
    [projectDir, activeFile],
  );

  const handleCompact = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const { merged } = await compactCacheLogs(projectDir);
      setJobLog((prev) => [...prev, `已合并 ${merged} 个翻译日志`]);
      await refreshFiles(projectDir);
      void loadPage(projectDir, activeFile, filter);
    } catch (err) {
      setError(err instanceof PipelineApiError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  }, [projectDir, refreshFiles, loadPage, activeFile, filter]);

  const handleRebuild = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      await rebuildCacheOutput(projectDir, files.some((f) => f.has_append));
      setJobLog((prev) => [...prev, '已提交重建输出任务…']);
    } catch (err) {
      setError(err instanceof PipelineApiError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  }, [projectDir, files]);

  const totalPages = page ? Math.max(1, Math.ceil(page.total / page.page_size)) : 1;
  const statLine = page
    ? `共 ${page.stats.entries} 条 · 锁定 ${page.stats.locked} · 问题 ${page.stats.problems} · 未翻译 ${page.stats.untranslated}`
    : '';

  return (
    <div className="page patch-page patch-editor">
      <PageHeader
        title="双语对照编辑器"
        description="直接修改缓存中的译文并锁定;重建输出后生效。锁定条目在后续翻译中不会被覆盖。"
      />

      {error && <div className="patch-page__error">{error}</div>}

      {!ready ? (
        <Panel title="连接后端">
          <p>正在向后端请求流水线凭据…</p>
        </Panel>
      ) : (
        <>
          <Panel title="① 选择工程">
            <div className="patch-page__row">
              <input
                className="patch-page__input"
                value={projectDir}
                onChange={(event) => setProjectDir(event.target.value)}
                placeholder="汉化工程目录(如 游戏_patch)"
              />
              <Button onClick={() => void handleBrowseProject()}>浏览…</Button>
              <Button
                variant="secondary"
                disabled={!projectDir.trim()}
                onClick={() => void loadProject(projectDir.trim())}
              >
                加载缓存
              </Button>
            </div>
            {files.length > 0 && (
              <div className="patch-editor__files">
                {files.map((file) => (
                  <button
                    key={file.name}
                    type="button"
                    className={`patch-editor__file${file.name === activeFile ? ' is-active' : ''}`}
                    onClick={() => handlePickFile(file.name)}
                  >
                    <span className="patch-editor__file-name">{file.name}</span>
                    <span className="patch-page__muted">
                      {file.entries} 条{file.locked > 0 ? ` · 锁 ${file.locked}` : ''}
                      {file.untranslated > 0 ? ` · 未译 ${file.untranslated}` : ''}
                      {file.has_append ? ' · 有未合并日志' : ''}
                    </span>
                  </button>
                ))}
              </div>
            )}
            {files.length === 0 && projectDir && (
              <p className="patch-page__muted">
                该工程还没有翻译缓存(先在补丁工作台跑到「AI 翻译」步)。
              </p>
            )}
          </Panel>

          {page && activeFile && (
            <Panel title={`② ${activeFile}(${statLine})`}>
              <div className="patch-editor__toolbar">
                <input
                  className="patch-page__input patch-editor__search"
                  value={filter.q}
                  placeholder="搜索原文/译文/角色…"
                  onChange={(event) => setFilter((prev) => ({ ...prev, q: event.target.value }))}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void handleFilterChange({ q: filter.q });
                  }}
                />
                <Button variant="secondary" onClick={() => void handleFilterChange({ q: filter.q })}>
                  搜索
                </Button>
                <label className="patch-editor__check">
                  <input
                    type="checkbox"
                    checked={filter.locked}
                    onChange={(event) => void handleFilterChange({ locked: event.target.checked })}
                  />
                  只看锁定
                </label>
                <label className="patch-editor__check">
                  <input
                    type="checkbox"
                    checked={filter.problem}
                    onChange={(event) => void handleFilterChange({ problem: event.target.checked })}
                  />
                  只看问题
                </label>
                <label className="patch-editor__check">
                  <input
                    type="checkbox"
                    checked={filter.untranslated}
                    onChange={(event) =>
                      void handleFilterChange({ untranslated: event.target.checked })
                    }
                  />
                  只看未翻译
                </label>
                <span className="patch-editor__spacer" />
                <Button
                  variant="secondary"
                  disabled={busy || jobRunning || !editable}
                  onClick={() => void handleCompact()}
                  title="把中断翻译遗留的 .append 日志合并进缓存"
                >
                  合并日志
                </Button>
                <Button
                  disabled={busy || jobRunning || !editable}
                  onClick={() => void handleRebuild()}
                  title="从缓存重建 gt_output 与 work/translated(不调用 API)"
                >
                  重建输出
                </Button>
              </div>

              {!editable && (
                <p className="patch-page__error">有任务正在运行,当前缓存为只读。</p>
              )}
              {files.some((f) => f.name === activeFile && f.has_append) && (
                <p className="patch-page__error">
                  该文件存在未合并的翻译日志:请先点「合并日志」再编辑,否则修改会丢失。
                </p>
              )}

              <div className="patch-editor__grid">
                <div className="patch-editor__row patch-editor__row--head">
                  <span>#</span>
                  <span>角色</span>
                  <span>原文</span>
                  <span>译文(修改保存后自动锁定)</span>
                  <span>锁定</span>
                  <span>状态</span>
                </div>
                {page.entries.map((entry) => {
                  const row = rows[entry.index] ?? entry;
                  const state = rowState[entry.index];
                  return (
                    <div key={entry.index} className="patch-editor__row">
                      <span className="patch-page__muted">{entry.index}</span>
                      <span className="patch-page__muted">{entry.name || '-'}</span>
                      <span className="patch-editor__src">
                        {row.pre_src}
                        {entry.problem && (
                          <button
                            type="button"
                            className={`patch-editor__problem pstatus-${row.problem_status || 'none'}`}
                            title={`${entry.problem}\n(点击切换:确认 → 忽略 → 清除)`}
                            onClick={() => void cycleProblemStatus(entry)}
                          >
                            ⚠{row.problem_status === 'confirmed'
                              ? '已确认'
                              : row.problem_status === 'ignored'
                                ? '已忽略'
                                : ''}
                          </button>
                        )}
                      </span>
                      <textarea
                        className="patch-editor__dst"
                        value={row.pre_dst}
                        disabled={!editable}
                        onChange={(event) => {
                          const value = event.target.value;
                          setRows((prev) => ({
                            ...prev,
                            [entry.index]: { ...row, pre_dst: value },
                          }));
                          setRowState((prev) => ({
                            ...prev,
                            [entry.index]: { dirty: true, saving: false, saved: false, error: '' },
                          }));
                        }}
                        onBlur={() => {
                          if (state?.dirty && row.pre_dst !== entry.pre_dst) {
                            void saveRow(entry, { pre_dst: row.pre_dst, locked: true });
                          }
                        }}
                      />
                      <input
                        type="checkbox"
                        checked={row.locked}
                        disabled={!editable}
                        onChange={(event) =>
                          void saveRow(entry, { locked: event.target.checked })
                        }
                      />
                      <span className={`patch-editor__state${state?.error ? ' has-error' : ''}`}>
                        {state?.error
                          ? '失败'
                          : state?.saving
                            ? '保存中…'
                            : state?.saved
                              ? '已保存 ✓'
                              : state?.dirty
                                ? '未保存'
                                : ''}
                      </span>
                    </div>
                  );
                })}
              </div>

              <div className="patch-editor__pager">
                <Button
                  variant="secondary"
                  disabled={(page?.page ?? 1) <= 1}
                  onClick={() => void loadPage(projectDir, activeFile, filter, (page?.page ?? 1) - 1)}
                >
                  ← 上一页
                </Button>
                <span className="patch-page__muted">
                  第 {page?.page ?? 1} / {totalPages} 页(筛选命中 {page?.total ?? 0} 条)
                </span>
                <Button
                  variant="secondary"
                  disabled={(page?.page ?? 1) >= totalPages}
                  onClick={() => void loadPage(projectDir, activeFile, filter, (page?.page ?? 1) + 1)}
                >
                  下一页 →
                </Button>
              </div>
            </Panel>
          )}

          {jobLog.length > 0 && (
            <Panel title="后台任务">
              <div className="patch-page__log">
                {jobLog.map((line, index) => (
                  <div key={`${index}-${line.slice(0, 12)}`}>{line}</div>
                ))}
              </div>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}
