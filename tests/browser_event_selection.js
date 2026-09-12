// 在 tests.browser_app 模拟服务上通过 Playwright browser_run_code_unsafe 运行。
async (page) => {
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  await page.goto('http://127.0.0.1:8001');
  await page.locator('.event-rule').first().waitFor();
  const total = await page.locator('.event-rule').count();
  const reload = async () => {
    await page.reload();
    await page.locator('.event-rule').first().waitFor();
  };
  await page.getByRole('button', {name:'清空选择', exact:true}).click();
  await reload();
  assert(await page.locator('.event-rule input:checked').count() === 0, '刷新保留空选择');
  await page.locator('.event-rule input').first().check();
  const code = await page.locator('.event-rule').first().getAttribute('data-code');
  await reload();
  assert(await page.locator('.event-rule input:checked').count() === 1, '刷新保留单项选择');
  assert(await page.locator('.event-rule:has(input:checked)').getAttribute('data-code') === code, '恢复相同事件');
  await page.getByRole('button', {name:'全选', exact:true}).click();
  await reload();
  assert(await page.locator('.event-rule input:checked').count() === total, '刷新保留全选');
  await page.getByRole('button', {name:'清空选择', exact:true}).click();
  await page.getByRole('button', {name:'恢复默认', exact:true}).click();
  await reload();
  assert(await page.locator('.event-rule input:checked').count() === total, '恢复默认覆盖保存的选择');
  return {passed:true, total};
}
