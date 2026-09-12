// 在 tests.browser_app 模拟服务上通过 Playwright browser_run_code_unsafe 运行。
async (page) => {
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  await page.goto('http://127.0.0.1:8001');
  await page.bringToFront();
  await page.locator('.event-rule').first().waitFor();
  await page.getByRole('button', {name:'恢复默认', exact:true}).click();
  const total = await page.locator('.event-rule').count();
  const reload = async () => {
    await page.reload();
    await page.bringToFront();
    await page.locator('.event-rule').first().waitFor({state:'attached'});
  };
  await page.getByRole('button', {name:'清空选择', exact:true}).click();
  await reload();
  assert(await page.locator('.event-rule > input:checked').count() === 0, '刷新保留空选择');
  await page.locator('.event-rule > input').first().check();
  const code = await page.locator('.event-rule').first().getAttribute('data-code');
  await reload();
  assert(await page.locator('.event-rule > input:checked').count() === 1, '刷新保留单项选择');
  assert(await page.locator('.event-rule:has(> input:checked)').getAttribute('data-code') === code, '恢复相同事件');
  await page.locator('.event-tile').first().click();
  await page.locator('.event-tile').nth(1).click();
  await page.locator('#events-selected').check();
  await reload();
  assert(await page.locator('#events-selected').isChecked(), '刷新恢复只看已选');
  assert(await page.locator('.event-rule:visible').count() === 1, '恢复过滤后的列表');
  assert(await page.locator('.event-tile[aria-pressed="true"]').count() === 2, '已选及未选事件的切片设置均恢复');
  assert(await page.evaluate(() => JSON.parse(document.getElementById('prompt').value).events.filter(e => e.tile_detection).length) === 2, '恢复的切片同步至 JSON');
  await page.getByRole('button', {name:'清空选择', exact:true}).click();
  await reload();
  assert(await page.locator('#events-selected').isChecked() && await page.locator('.event-rule:visible').count() === 0, '空选择和过滤共同恢复');
  await page.locator('#events-selected').uncheck();
  await page.locator('.event-tile').first().click();
  await reload();
  assert(!await page.locator('#events-selected').isChecked(), '刷新保留关闭过滤');
  assert(await page.locator('.event-tile').first().getAttribute('aria-pressed') === 'false', '刷新保留关闭切片');
  await page.getByRole('button', {name:'全选', exact:true}).click();
  await reload();
  assert(await page.locator('.event-rule > input:checked').count() === total, '刷新保留全选');
  await page.getByRole('button', {name:'清空选择', exact:true}).click();
  await page.getByRole('button', {name:'恢复默认', exact:true}).click();
  await reload();
  assert(await page.locator('.event-rule > input:checked').count() === total, '恢复默认覆盖保存的选择');
  assert(!await page.locator('#events-selected').isChecked() && await page.locator('.event-tile[aria-pressed="true"]').count() === 0, '恢复默认同时重置过滤与切片');
  return {passed:true, total};
}
