// Optional local browser check: PLAYWRIGHT_CORE=/path/to/playwright-core node tests/test_combat_graph_browser.js REPORT.html
const assert = require("node:assert/strict");
const { chromium } = require(process.env.PLAYWRIGHT_CORE || "playwright-core");
const { pathToFileURL } = require("node:url");
const path = require("node:path");
(async () => {
  const browser = await chromium.launch({executablePath:"/usr/bin/google-chrome",
    headless:true,args:["--no-sandbox","--disable-gpu"]});
  try {
    for (const [width,height] of [[1440,900],[2560,1440]]) {
      const page = await browser.newPage({viewport:{width,height}});
      const errors=[];
      page.on("pageerror",error=>errors.push(error.message));
      await page.route("http://**/*",route=>route.abort());
      await page.route("https://**/*",route=>route.abort());
      await page.goto(pathToFileURL(path.resolve(process.argv[2])).href);
      try {
        await page.waitForFunction(() => document.querySelectorAll("#graph .node").length > 0,
          {timeout:10000});
      } catch(error) {
        console.log("layout status",await page.locator("#layout-status").innerText(),"errors",errors);
        throw error;
      }
      assert.equal(await page.locator("#graph .node").count(),5);
      assert.equal(await page.locator("#graph .link").count(),6);
      assert.equal(await page.locator("#graph .link.reference").count(),3);
      assert.equal(await page.locator("#graph .link[data-edge='edge:5'] path").count(),1);
      assert.equal(await page.locator(".action-row").count(),3);
      await page.screenshot({path:"/tmp/silver-viewer-initial-"+width+"x"+height+".png"});
      await page.locator(".node[data-node='2']").click();
      assert.match(await page.locator("#inspector-content").innerText(),/State #2/);
      await page.screenshot({path:"/tmp/silver-viewer-shared-"+width+"x"+height+".png"});
      const transform=await page.locator("#graph-layer").getAttribute("transform");
      await page.locator("#zoom-in").click();
      await page.waitForTimeout(350);
      assert.notEqual(await page.locator("#graph-layer").getAttribute("transform"),transform);
      await page.locator("#root-filter").selectOption("edge:2");
      await page.waitForFunction(() => document.querySelectorAll("#graph .link").length===4);
      assert.equal(await page.locator(".action-row").count(),3);
      await page.locator("#root-filter").selectOption("");
      await page.waitForFunction(() => document.querySelectorAll("#graph .link").length===6);
      await page.locator("#search").fill("1002");
      assert.equal(await page.locator("#search-results button").count(),2);
      await page.locator("#search-results button").first().click();
      assert.match(await page.locator("#inspector-content").innerText(),/State #2/);
      await page.locator("#minimap").click({position:{x:50,y:50}});
      await page.locator("#graph .link[data-edge='edge:3'] path").click({force:true});
      assert.match(await page.locator("#inspector-content").innerText(),/Chance outcome/);
      await page.screenshot({path:"/tmp/silver-viewer-chance-"+width+"x"+height+".png"});
      await page.locator("#graph .node[data-node='2']").click({force:true});
      await page.locator("#focus").click();
      await page.waitForFunction(() => document.querySelectorAll("#graph .node").length===1);
      await page.locator("#back").click();
      await page.waitForFunction(() => document.querySelectorAll("#graph .node").length===5);
      await page.locator("#fit").click();
      await page.waitForTimeout(350);
      await page.screenshot({path:"/tmp/silver-viewer-normal-"+width+"x"+height+".png"});
      await page.locator("#fullscreen").click();
      await page.screenshot({path:"/tmp/silver-viewer-"+width+"x"+height+".png"});
      assert.deepEqual(errors,[]);
      console.log(width+"x"+height+": 5 nodes, 6 edges, offline, interactions, no errors");
      await page.close();
    }
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
