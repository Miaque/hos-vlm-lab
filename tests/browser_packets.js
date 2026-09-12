// 在 tests.browser_app 上运行，报文夹具明确为模拟，不调用真实模型。
async (page) => {
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  await page.bringToFront();
  await page.goto('http://127.0.0.1:8001');
  await page.bringToFront();
  await page.locator('.event-rule').first().waitFor();
  await page.getByRole('button', {name:'恢复默认', exact:true}).click();
  await page.locator('#files').evaluate(input => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 4;
    return new Promise(resolve => canvas.toBlob(blob => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([blob], 'packet-test.png', {type:'image/png'}));
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', {bubbles:true}));
      resolve();
    }));
  });
  await page.locator('#image-count').filter({hasText:'1 / 20'}).waitFor();
  await page.getByRole('button', {name:'开始对比',exact:true}).click();
  await page.waitForFunction(() => state.round?.status === 'completed', null, {polling:100});
  await page.bringToFront();
  const open = page.locator('.packet-open').first();
  assert(await open.evaluate(button => {
    const icon = button.getBoundingClientRect();
    const title = button.parentElement.querySelector('h3').getBoundingClientRect();
    return icon.width === 26 && Math.abs(icon.y + icon.height / 2 - title.y - title.height / 2) < 1;
  }), '小图标与标题垂直居中');
  await open.click();
  await page.locator('#packet-content').getByText(/没有记录完整请求报文/).waitFor();
  assert(await page.locator('#packet-copy').isDisabled(), '旧记录不能伪造请求');
  await page.keyboard.press('Escape');
  assert(!await page.locator('#packet-dialog').isVisible(), 'Escape 关闭');
  const rawRequest = JSON.stringify({model:'模拟模型', messages:[{role:'user', content:[{type:'text', text:'模拟提示词\n第二行 <img src=x onerror=alert(1)>'}, {type:'image_url', image_url:{url:'data:image/jpeg;base64,'+'A'.repeat(3000)}}]}], max_tokens:123});
  const rawResponse = JSON.stringify({choices:[{message:{content:JSON.stringify({events:[]})}}], usage:{prompt_tokens:456}});
  const pattern = '**/api/attempts/*';
  await page.route(pattern, async route => {
    const original = await route.fetch();
    await route.fulfill({json:{...await original.json(), request_body:rawRequest, raw_response:rawResponse,
      request_http:{method:'POST',url:'https://simulation.invalid/v1/chat/completions',headers:{authorization:'[REDACTED]'}},
      response_http:{status_code:200,headers:{'x-request-id':'simulated'}}}});
  });
  try {
    await open.click();
    await page.locator('#packet-meta').getByText(/simulation.invalid/).waitFor();
    assert(await page.locator('#packet-format').inputValue() === 'json', '每次打开默认 JSON 格式');
    await page.locator('#packet-format').selectOption('read');
    await page.locator('#packet-content summary').filter({hasText:'messages'}).click();
    // 阅读树允许按层级展开，完整原文不受折叠状态影响。
    await page.locator('#packet-format').selectOption('json');
    const compact = await page.locator('#packet-content pre').textContent();
    assert(compact.includes('图片数据已折叠：3000') && !compact.includes('A'.repeat(3000)), 'JSON 默认折叠图片');
    assert(JSON.parse(compact).max_tokens === 123, '其他 JSON 字段保留');
    await page.locator('#packet-images').check();
    assert(await page.locator('#packet-content pre').textContent() === JSON.stringify(JSON.parse(rawRequest), null, 2), '请求 JSON 标准缩进且完整');
    await page.locator('#packet-images').uncheck();
    await page.locator('#packet-format').selectOption('raw');
    assert(await page.locator('#packet-content pre').textContent() === rawRequest, '请求原文完整');
    assert(await page.locator('#packet-content img').count() === 0, '报文不得作为 HTML 执行');
    // 测试浏览器不支持授予剪贴板权限；验证复制接口收到完整文本，不覆盖用户剪贴板。
    await page.evaluate(() => {
      navigator.clipboard.writeText = async text => { window.packetCopiedText = text; };
    });
    await page.locator('#packet-copy').click();
    await page.locator('#packet-note').getByText(/已复制/).waitFor();
    assert(await page.evaluate(() => window.packetCopiedText) === rawRequest, '复制完整正文');
    await page.locator('#packet-response').click();
    assert(await page.locator('#packet-content pre').textContent() === rawResponse, '响应原文完整');
    await page.locator('#packet-format').selectOption('json');
    assert(await page.locator('#packet-content pre').textContent() === JSON.stringify(JSON.parse(rawResponse), null, 2), '响应 JSON 格式');
    await page.locator('#packet-format').selectOption('read');
    assert(await page.locator('#packet-content').getByText('content · JSON 字符串（阅读视图）').count() === 1, '响应内 JSON 字符串可读');
    for (const width of [1440,390]) {
      await page.setViewportSize({width,height:900});
      assert(await page.locator('#packet-dialog').evaluate(el => el.getBoundingClientRect().right <= innerWidth && el.getBoundingClientRect().bottom <= innerHeight), '弹窗适配视口');
    }
    await page.locator('#packet-close').click();
    assert(!await page.locator('#packet-dialog').isVisible(), '关闭按钮');
  } finally { await page.unroute(pattern); }
  return {passed:true, checks:'旧记录、请求响应切换、完整原文和复制、嵌套 JSON、安全文本、Escape 和关闭、桌面手机布局'};
}
