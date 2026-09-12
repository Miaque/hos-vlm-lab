// 在 tests.browser_app 模拟服务运行，不调用真实模型。
async (page) => {
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  await page.bringToFront();
  await page.goto('http://127.0.0.1:8001');
  await page.bringToFront();
  await page.locator('.event-rule').first().waitFor();
  await page.getByRole('button', {name:'恢复默认',exact:true}).click();
  await page.locator('#files').evaluate(async input => {
    const transfer = new DataTransfer();
    for (let i = 0; i < 3; i++) {
      const canvas = document.createElement('canvas');
      canvas.width = 320; canvas.height = 160;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = ['red','green','blue'][i]; ctx.fillRect(0,0,320,160);
      const blob = await new Promise(resolve => canvas.toBlob(resolve));
      transfer.items.add(new File([blob], `navigation-${i + 1}.png`, {type:'image/png'}));
    }
    input.files = transfer.files;
    input.dispatchEvent(new Event('change', {bubbles:true}));
  });
  await page.locator('#image-count').filter({hasText:'3 / 20'}).waitFor();
  await page.getByRole('button', {name:'开始对比',exact:true}).click();
  await page.waitForFunction(() => state.round?.status === 'completed');
  const checkImage = async index => {
    assert((await page.locator('#result-image-name').textContent()).includes(`第 ${index + 1} / 3 张`), '图片序号');
    assert(await page.locator('#result-thumbnails button[aria-pressed="true"]').count() === 1, '唯一选中缩略图');
    await page.locator('.packet-open').first().click();
    assert((await page.locator('#packet-context').textContent()).includes(`navigation-${index + 1}.png`), '报文对应当前图片');
    await page.keyboard.press('Escape');
  };
  for (const width of [1440,390,320]) {
    await page.setViewportSize({width,height:900});
    await page.locator('#result-thumbnails .result-select').first().click();
    assert(await page.locator('#result-prev').isDisabled(), '首张禁用上一张');
    await page.locator('#result-next').click();
    await checkImage(1);
    assert(await page.evaluate(() => {
      const nav = document.querySelector('#result-nav').getBoundingClientRect();
      const results = document.querySelector('#results').getBoundingClientRect();
      return nav.top >= -1 && results.top >= nav.bottom && results.top < innerHeight;
    }), '切图后结果起点可见且不被吸顶栏遮挡');
    await page.evaluate(() => window.scrollTo({top: scrollY + document.querySelector('#result-nav').getBoundingClientRect().top + 80, behavior:'instant'}));
    assert(await page.locator('#result-nav').evaluate(el => Math.abs(el.getBoundingClientRect().top) < 2), '结果阅读时吸顶');
    await page.locator('#result-next').click();
    await checkImage(2);
    assert(await page.locator('#result-next').isDisabled(), '末张禁用下一张');
    const before = await page.evaluate(() => scrollY);
    await page.locator('.result-thumbnail').nth(0).hover();
    await page.locator('.thumbnail-zoom').nth(0).click();
    assert(await page.evaluate(() => state.selected === state.images[2].id), '放大其他图片不切换当前结果');
    assert(await page.locator('#result-original').evaluate(img => img.src === new URL(state.images[0].original_url,location.href).href), '放大对应原图');
    await page.keyboard.press('Escape');
    assert(Math.abs(await page.evaluate(() => scrollY) - before) < 2, '关闭放大保留滚动位置');
    assert(await page.locator('#result-nav').evaluate(nav => nav.getBoundingClientRect().right <= innerWidth && nav.scrollWidth <= nav.clientWidth), '结果导航没有横向溢出');
    if (width >= 390) assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), '页面没有横向溢出');
  }
  return {passed:true, checks:'三图切换、结果与报文对应、首尾禁用、吸顶、原图放大和位置恢复、1440/390/320px'};
}
