// 启动 uv run python -m tests.browser_app 后，用 Playwright browser_run_code_unsafe 的 filename 运行。
async (page) => {
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  await page.goto('http://127.0.0.1:8001');
  await page.locator('.event-rule').first().waitFor();
  assert(await page.evaluate(() => formatTime('2026-09-12T16:00:00Z')) === '2026年09月13日 00:00:00', '北京时间跨日及24小时制');
  const total = await page.locator('.event-rule').count();
  assert(total > 1, '事件应逐项展示');
  await page.getByRole('button', { name: '清空选择', exact: true }).click();
  assert(await page.evaluate(() => {
    try { selectedPrompt(); return false; } catch { return true; }
  }), '空选择必须拦截');
  const first = page.locator('.event-rule').first();
  await first.locator('input').check();
  await page.locator('#events-selected').check();
  assert(await page.locator('.event-rule:visible').count() === 1, '只看已选');
  await page.locator('#events-selected').uncheck();
  await first.locator('button').click();
  await page.locator('#event-detail section:visible textarea').first().fill('本轮微调：只依据清晰的可见证据。');
  await page.locator('.event-rule button').nth(1).click();
  await first.locator('button').click();
  assert((await page.locator('#event-detail section:visible textarea').first().inputValue()).includes('本轮微调'), '切换事件保留草稿');
  const selected = await page.evaluate(() => JSON.parse(selectedPrompt()));
  assert(selected.events.length === 1, '仅提交已选事件');
  assert(selected.events[0].match.includes('本轮微调'), '单项编辑应进入提交内容');
  assert(await page.evaluate(() => JSON.parse(document.getElementById('prompt').value).events.length) === total, '未选事件仍保留');
  await page.locator('#event-search').fill(selected.events[0].code);
  assert(await page.locator('.event-rule:visible').count() === 1, '搜索编码');
  await page.locator('#event-search').fill('不存在的事件');
  assert(await page.locator('.event-rule:visible').count() === 0, '搜索无结果');
  await page.locator('#event-search').fill('');
  await page.locator('#files').evaluate(input => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 4;
    return new Promise(resolve => canvas.toBlob(blob => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([blob], 'sample.png', {type:'image/png'}));
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', {bubbles:true}));
      resolve();
    }));
  });
  await page.locator('#image-count').filter({hasText:'1 / 20'}).waitFor();
  const request = page.waitForRequest(r => r.url().endsWith('/api/rounds') && r.method() === 'POST');
  await page.getByRole('button', {name:'开始对比',exact:true}).click();
  const submitted = JSON.parse((await request).postDataJSON().prompt_text);
  assert(submitted.events.length === 1 && submitted.events[0].match === selected.events[0].match, '实际请求使用已选规则');
  await page.waitForFunction(() => state.round?.status === 'completed');
  const frozen = await page.evaluate(() => state.round);
  assert(Object.keys(frozen.event_snapshot).length === 1 && frozen.rendered_prompt_text.includes('本轮微调'), '后端冻结选择与编辑');
  await page.getByRole('button', {name:'恢复默认',exact:true}).click();
  assert(await page.locator('.event-rule input:checked').count() === total, '恢复默认全选');
  assert(await page.evaluate(() => state.round.rendered_prompt_text) === frozen.rendered_prompt_text, '历史快照不变');
  await page.locator('#prompt-source summary').click();
  await page.locator('#prompt').fill('{');
  assert(await page.locator('#event-error').isVisible(), '非法 JSON 提示');
  await page.locator('#prompt').fill(JSON.stringify({events:[{code:'custom',name:'自定义',match:'原条件',extra:{a:1}}],context:'保留上下文'}));
  assert(await page.locator('.event-rule').count() === 1, '自定义事件同步');
  await page.locator('.event-rule button').click();
  await page.getByRole('textbox', {name:'自定义 · extra',exact:true}).fill('{');
  await page.getByRole('button', {name:'全选',exact:true}).click();
  assert(await page.evaluate(() => { try { selectedPrompt(); return false; } catch { return true; } }), '无效嵌套值不可静默丢弃');
  await page.getByRole('textbox', {name:'自定义 · extra',exact:true}).fill('{"a":2}');
  assert(await page.evaluate(() => JSON.parse(selectedPrompt()).context) === '保留上下文', '额外上下文保留');
  await page.getByRole('button', {name:'恢复默认',exact:true}).click();
  await page.locator('#prompt-source summary').click();
  await page.setViewportSize({width:1440,height:1000});
  assert(await page.evaluate(() => Math.abs(document.querySelector('.image-panel').getBoundingClientRect().bottom - document.querySelector('.input-panel').getBoundingClientRect().bottom) < 1), '图片与模型面板底部对齐');
  await page.locator('.event-rule button').first().click();
  await page.screenshot({path:'.test-data/event-editor-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), '移动端整页不能横向溢出');
  await page.screenshot({path:'.test-data/event-editor-mobile.png',fullPage:true});
  return {passed:true,total,checks:'选择、微调、搜索、真实本地请求与快照、恢复默认、JSON 同步与错误、移动端布局'};
}
