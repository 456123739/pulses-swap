(async () => {
  const results = [];
  const check = (name, ok, detail = '') => {
    results.push({ name, ok: Boolean(ok), detail: String(detail || '') });
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const call = async (method, params = {}) => {
    const res = await window.pywebview.api.invoke(method, params);
    if (!res || !res.ok) throw new Error(`${method}: ${res?.error?.message || 'failed'}`);
    return res.data;
  };
  const state = async () => call('app.bootstrap');
  const waitState = async (predicate, timeout = 12000) => {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      const s = await state();
      if (predicate(s)) return s;
      await sleep(250);
    }
    throw new Error('state wait timeout');
  };
  try {
    check('bridge.invoke', typeof window.pywebview?.api?.invoke === 'function');
    check('bridge.pending_drop', typeof window.pywebview?.api?.handle_drop_pending === 'function');
    let s = await state();
    check('bootstrap', s && Array.isArray(s.presets), s?.version);
    check('main-no-onboarding', !!document.querySelector('.empty-hero') && !document.querySelector('.hero-empty'));

    // 页面导航
    for (const [i, h1] of [[1, '管理'], [2, '设置'], [3, '日志'], [0, '枪包预设']]) {
      document.querySelectorAll('.nav-item')[i]?.click();
      await sleep(1300);
      check(`nav.${h1}`, document.querySelector('h1')?.innerText === h1);
      check(`nav.${h1}.no-cover`, !document.querySelector('.cover'));
    }

    // 侧栏悬停（管理页）
    document.querySelectorAll('.nav-item')[1]?.click();
    await sleep(1300);
    const sidebar = document.querySelector('.sidebar');
    sidebar?.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, relatedTarget: document.body }));
    sidebar?.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
    await sleep(500);
    check('sidebar.hover-manage', sidebar && getComputedStyle(sidebar).width === '200px', sidebar && getComputedStyle(sidebar).width);
    check('sidebar.role-switch', !!document.querySelector('.role-switch'));
    const rs = document.querySelector('.role-switch');
    check('role.logged-out-label', !!rs && rs.innerText.includes('未登录') && rs.innerText.includes('无法切换身份'), rs?.innerText);
    rs?.click();
    await sleep(220);
    check('role.login-opened', document.querySelectorAll('.modal-card input').length >= 2);
    check('role.login-title', (document.querySelector('#modal-title')?.innerText || '').includes('登录蓝奏云'));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await sleep(150);

    // 打开测试整合包
    await call('pack.open', { path: window.__SELFTEST_PACK });
    s = await waitState((x) => x.pack.loaded);
    check('pack.loaded', s.pack.loaded, s.pack.name);
    document.querySelectorAll('.nav-item')[0]?.click();
    await sleep(1200);
    check('home.applied-hidden', !document.querySelector('button.hero-primary') && !!document.querySelector('.applied-state'));

    // 新建预设后应出现一键替换；再推一次，避免 pack.open 的 job.done 晚到覆盖
    const created = await call('preset.create', { name: 'CI 自测预设' });
    window.PS.push({ type: 'state.changed', data: { state: created } });
    s = await waitState((x) => x.selected === 'CI 自测预设');
    await sleep(700);
    window.PS.push({ type: 'state.changed', data: { state: created } });
    await sleep(350);
    check('home.apply-button', !!document.querySelector('button.hero-primary'), document.body.innerText.slice(0, 80));

    // 右键预设详情，关闭不保存
    const presetRow = document.querySelector('.preset-row');
    presetRow?.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true }));
    await sleep(450);
    check('preset.detail-open', (document.querySelector('#modal-title')?.innerText || '') === '预设详情');
    check('preset.detail-fields', document.querySelectorAll('.preset-detail-fields input').length === 2);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await sleep(150);

    // 玩家从云端拉取预设弹窗
    const pullBtn = [...document.querySelectorAll('button')].find((b) => b.innerText.includes('从云端拉取预设'));
    check('player.pull-button', !!pullBtn);
    pullBtn?.click();
    await sleep(180);
    check('player.pull-dialog', (document.querySelector('#modal-title')?.innerText || '').includes('从云端添加预设'));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await sleep(150);

    // 设置：高级操作开关
    document.querySelectorAll('.nav-item')[2]?.click();
    await sleep(1300);
    const advanced = document.querySelector('.switch[aria-label="高级操作"]');
    check('settings.advanced-switch', !!advanced);
    advanced?.click();
    await sleep(250);
    check('settings.advanced-on', advanced?.getAttribute('aria-checked') === 'true');
    advanced?.click();
    await sleep(200);
    check('settings.advanced-off', advanced?.getAttribute('aria-checked') === 'false');

    // 日志清空
    document.querySelectorAll('.nav-item')[3]?.click();
    await sleep(1300);
    const clear = [...document.querySelectorAll('button')].find((b) => b.innerText.trim() === '清空');
    check('log.clear-button', !!clear);
    clear?.click();
    await sleep(350);
    s = await state();
    check('log.cleared', Array.isArray(s.logs) && s.logs.length === 0, s.logs?.length);

    // 云按钮存在（CI 无账号，不执行网络）
    document.querySelectorAll('.nav-item')[1]?.click();
    await sleep(1300);
    check('manage.one-click', !!document.querySelector('.manage-action .action-primary'));
    check('manage.plan-guard', !!document.querySelector('.plan-card'));
    check('no-scrollbar', getComputedStyle(document.querySelector('.content')).scrollbarWidth === 'none');

    await call('app.selftest.report', { ok: results.every((r) => r.ok), results });
  } catch (err) {
    results.push({ name: 'selftest.exception', ok: false, detail: String(err && err.stack || err) });
    try { await call('app.selftest.report', { ok: false, results }); } catch (_) {}
  }
})()
