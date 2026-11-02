/** @odoo-module **/
// Public, fictional examples. This handbook never reads business records.
export const GUIDE_DETAILS = {
 overview: {
  fields: [
   {field:'Company',meaning:['اختار الشركة من قائمة Odoo فوق. أرقام الـDashboard تخص الشركة الحالية فقط، حتى لو عندك أكتر من شركة مسموحة.','Choose the company in the Odoo company selector. Dashboard figures belong to the current company, even when several companies are allowed.']},
   {field:'Period',meaning:['شهر الفاتورة أو المرتجع حسب Invoice Date؛ ولو مش موجود بيستخدم Accounting Date. المرتجع في شهر جديد بيقلل أرقام الشهر الجديد.','The month of Invoice Date, falling back to Accounting Date. A refund in a later month reduces that later month.']},
   {field:'Region / team',meaning:['All accessible teams يعرض النطاق المسموح. اختيار منطقة يضم الفرق التابعة لها. الفرق اللي بتقودها بتظهر حتى لو لسه مفيهاش حركة.','All accessible teams uses your permitted scope. Selecting a region includes descendants. Teams you lead appear even before any activity.']},
   {field:'Net invoiced',meaning:['صافي سطور المنتجات بعد الخصم ومن غير ضريبة، ناقص المرتجعات، بعملة الشركة. ده مبلغ المبيعات، مش مبلغ العمولة.','Product-line net after discount and before tax, less refunds, in company currency. This is revenue, not commission.']},
   {field:'Net commission',meaning:['مجموع العمولات المحسوبة ناقص عمولات المرتجعات. السطور Needs review عمولتها صفر لحد تصحيح السبب وإعادة المحاولة.','Calculated commission less refund commission. Needs review rows contribute zero until their cause is corrected and retried.']},
   {field:'Credit note impact',meaning:['قيمة المبيعات اللي رجعت في الفترة، مش قيمة العمولة المخصومة. عشان تعرف خصم العمولة افتح سطور الـCredit notes في السجل.','Refunded sales value in the period, not the commission reduction. Open Credit notes in the ledger for refunded commission.']},
   {field:'Monthly target / Target achievement',meaning:['الهدف الشهري ونسبة صافي المبيعات إليه. Not set معناه مفيش هدف؛ النسبة ممكن تتعدى 100%. التارجت لا يغير نسبة العمولة.','Monthly goal and net-sales achievement. Not set means no target; achievement can exceed 100%. Targets never change commission rates.']},
   {field:'Needs review / Salesperson performance',meaning:['عدد السطور المحتاجة مراجعة، وتفصيل الأداء لكل مندوب. فتح التفاصيل يحافظ على نفس الشهر والفريق والصلاحيات.','Review-row count and per-person performance. Drilldowns preserve the month, team and access scope.']},
  ],
  checks:[['ابدأ بالشركة، ثم المناطق وTeam Leader، ثم أدوار المستخدمين، وتصنيفات المنتجات والخدمات، والقواعد المؤرخة، والتارجت. إعداد القيود المحاسبية خطوة اختيارية منفصلة.','Start with company, regions and Team Leader, then user roles, product/service categories, dated rules and targets. Accrual accounting is a separate optional setup.'],['جرّب فاتورة QA مرتبطة بأمر بيع، رحّلها، وراجع السجل والـDashboard. بعد كده جرّب مرتجع مرتبط بالفاتورة. للبيانات القديمة استخدم Calculate posted commissions صراحة.','Test a QA invoice linked to a sale order, post it, then check the ledger and dashboard. Test a linked credit note next. Use Calculate posted commissions explicitly for older data.']],
  example:{title:['مثال شهر كامل','A complete month'],headers:[['البند','Item'],['القيمة','Value'],['المعنى','Meaning']],rows:[
   [['مبيعات صافية قبل المرتجع','Net sales before refund'],'80,000',['بعد الخصم ومن غير ضريبة','After discount, before tax']],
   [['مرتجعات الشهر','Refunded sales'],'5,000',['Credit note impact','Credit note impact']],
   [['Net invoiced','Net invoiced'],'75,000',['80,000 − 5,000','80,000 − 5,000']],
   [['التارجت','Target'],'100,000',['الإنجاز = 75%','Achievement = 75%']],
  ],note:['المندوب بيشوف مساهمته هو فقط. المدير بيشوف مجموع الفرق المسموحة له. الأمثلة للشرح ومش سياسة العمولة الفعلية.','Salespeople see their own contribution. Managers see their permitted teams. Examples illustrate behavior; they are not your commission policy.']},
  questions:[
   {q:['الأرقام صفر مع إن فيه Sales Orders؟','Why are totals zero despite sale orders?'],a:['أمر البيع لوحده مش بيستحق عمولة. راجع إن فيه فاتورة عميل Posted، الشهر والشركة صح، وسبب Needs review. الفواتير القديمة مش بتتعملها عمولات تلقائي بمجرد تثبيت الموديول.','A sale order alone does not earn commission. Check for a posted customer invoice, the correct month/company and Needs review reasons. Installation does not automatically backfill old invoices.']},
   {q:['ليه أرقام مدير المنطقة أكبر من المندوب؟','Why does a manager see more than a salesperson?'],a:['المندوب بيشوف سطوره هو. المدير بيشوف سطوره وكمان نطاق الفرق اللي هو Team Leader عليها والمناطق الإضافية وفروعهم. مسؤول العمولات يشوف كل ما تسمح به شركاته.','Salespeople see their own rows. Managers additionally see teams they lead, additional assignments and descendants. Commission administrators see entries across their allowed companies.']},
   {q:['إزاي أستخدم القائمة اليمين والموبايل؟','How do I use navigation and mobile?'],a:['زر Navigation بيطوي القائمة لأيقونات. على الموبايل بيفتح لوحة جانبية وتقفلها من نفس الزر أو بالضغط خارجها. القائمة خاصة بالتطبيق؛ Guide فيه شرح كامل لكن فتح الشاشات حسب الدور.','Navigation collapses to icons. On mobile it opens a panel; close it with the same button or the backdrop. The sidebar is app-specific. Guide explains everything, while screen access follows your role.']},
  ],
 },
 ledger:{
  fields:[
   {field:'Date / Journal Entry / Invoice line',meaning:['التاريخ اللي عليه التقرير، ورابط الفاتورة، وسطر المنتج المصدر. كل سطر منتج له Snapshot واحد؛ سطور الضريبة والأقساط والعناوين مش سطور عمولة.','Reporting date, source invoice and source product line. Each product line has one snapshot. Tax, payment-term and section lines do not earn commission.']},
   {field:'Salesperson / Team',meaning:['المندوب والفريق من أمر البيع الأصلي، مش مجرد مندوب الفاتورة. لو السطر جاي من أكتر من أمر بيع لازم المندوب والفريق والشركة يتفقوا.','Attribution comes from the original sale order, not merely the invoice salesperson. Multiple source orders must agree on person, team and company.']},
   {field:'Product / Category Name / Rule',meaning:['المنتج، اسم تصنيفه وقت الحساب، والقاعدة المستخدمة. اسم الفئة والنسبة محفوظين علشان التعديلات اللاحقة مش تعيد كتابة الماضي.','Product, category label at calculation and the matched rule. The label and rate are snapshotted so later edits do not rewrite history.']},
   {field:'Net invoiced / Rate % / Commission',meaning:['الأساس الصافي بعملة الشركة، النسبة المحفوظة، وقيمة العمولة. المرتجع المرتبط بيستخدم نسبة الأصل وحصته من العمولة الأصلية.','Net company-currency base, captured rate and commission amount. Linked refunds use the original rate and their proportional share of original commission.']},
   {field:'Status / Note',meaning:['Calculated معناها السطر اتحسب، حتى لو نسبته صفر. Needs review معاه Note يوضح بيانات ناقصة أو ربط غامض؛ راجعه قبل معالجة السطور القديمة.','Calculated means processed, even at a zero rate. Needs review includes a Note describing missing data or ambiguous links; resolve it before retrying.']},
   {field:'Original commission',meaning:['في المرتجع رابط سطر العمولة الأصلي. الربط الدقيق بيتحفظ في المرتجعات الجديدة من Reverse؛ المرتجع اليدوي أو القديم لازم يتربط بأصل واضح غير ملتبس.','Refunds link to their original commission row. New Odoo reversals preserve exact line links. Older/manual credits need an unambiguous original match.']},
   {field:'Accounting Status / Accrual journal entry',meaning:['Needs review، Zero commission، Not booked أو Accrued. Accrued معناها قيد استحقاق Posted؛ مش معناها العمولة اتدفعت. فتح المستند محتاج صلاحية الحسابات العادية.','Needs review, Zero commission, Not booked or Accrued. Accrued means a posted liability entry, not payment. Opening it requires normal accounting document access.']},
  ],
  example:{title:['فاتورة ومرتجع بنسبة قديمة محفوظة','Invoice and refund with a preserved rate'],headers:[['الحركة','Movement'],['الأساس','Base'],['النسبة','Rate'],['العمولة','Commission']],rows:[
   [['منتج بعد خصم 10% من 2,000','Product after 10% discount on 2,000'],'1,800','10%','180'],
   [['خدمة VIP','VIP service'],'1,000','7%','70'],
   [['إجمالي الفاتورة بدون ضريبة','Untaxed invoice total'],'2,800','—','250'],
   [['مرتجع ربع المنتج','Refund of one quarter of the product'],'−450','10%','−45'],
   [['الصافي بعد المرتجع','Net after refund'],'2,350','—','205'],
  ],note:['ضريبة 15% على الفاتورة = 420؛ إجمالي الفاتورة 3,220، لكن العمولة على 2,800 فقط. لو النسبة اتغيرت بعد الفاتورة إلى 20%، المرتجع ده يفضل بنسبة الأصل 10%.','At 15% tax the invoice tax is 420 and total is 3,220, but commission uses only 2,800. If the rule later changes to 20%, this refund still uses the original 10%.']},
  questions:[
   {q:['لو رجع جزء من فاتورة بعملة أجنبية؟','What about foreign-currency partial refunds?'],a:['المبيعات بتتسجل برصيدها المرحّل بعملة الشركة. عمولة المرتجع بتعكس الحصة المناسبة من العمولة الأصلية؛ المرتجع الكامل يعكس العمولة الأصلية حتى لو سعر الصرف اتغير.','Sales reporting uses posted company-currency balances. Refund commission reverses the proportional original amount; a full refund reverses original commission even when exchange rates changed.']},
   {q:['لو عملت Reset to Draft أو Cancel؟','What happens on reset to draft or cancellation?'],a:['الـSnapshot بيتشال حسب حالة الفاتورة، وأي قيد استحقاق سابق بيتعكس بقيد محفوظ بتاريخ اليوم. إعادة الترحيل بتحسب من جديد بالقواعد السارية. لازم تعالج المرتجعات المرتبطة المرحّلة قبل إرجاع الأصل لمسودة، مع احترام قفل الحسابات.','Snapshots follow invoice state, while posted accruals are preserved and reversed with a dated-today entry. Reposting recalculates using applicable rules. Reset linked posted credit notes before their original invoice; accounting locks still apply.']},
   {q:['ينفع أعدل العمولة يدوي أو أكرر Book؟','Can I edit commission or book it twice?'],a:['السجل مش بيتعدل يدويًا حتى من مسؤول العمولة. صحح المصدر أو القاعدة، واستخدم مسار إعادة الحساب المناسب. تكرار الإثبات على سطر مثبت بالفعل مش بيعمل قيد مكرر.','Normal users, including commission administrators, cannot edit ledger rows. Correct the source/setup and use the appropriate recalculation flow. Rebooking an already accrued row does not duplicate its journal entry.']},
  ],
 },
 targets:{
  fields:[
   {field:'Company',meaning:['الشركة صاحبة الهدف، وعملتها هي عملة المبلغ. هدف شركة مش بيتجمع على Dashboard شركة تانية.','The target company determines currency. Its target is not included in another company’s dashboard.']},
   {field:'Team',meaning:['المنطقة أو المنطقة الفرعية أو الفرع. اربط المستويات الأول؛ إسناد هدف لمنطقة لا ينشئ أهدافًا تلقائيًا للفروع.','Choose a region, subregion or branch. Configure hierarchy first. A parent target does not automatically create branch targets.']},
   {field:'Month',meaning:['أول يوم من الشهر، مثل 01/11/2026. النظام بيرفض يوم مختلف علشان الهدف يبقى شهري وواضح.','Use the first day of the month, such as 01/11/2026. Other days are rejected so the goal remains explicitly monthly.']},
   {field:'Amount',meaning:['مبلغ موجب بعملة الشركة. فيه هدف واحد لكل شركة وفريق وشهر؛ إنشاء وتعديل الأهداف لمسؤول العمولات.','A positive company-currency amount. One goal per company/team/month; only commission administrators create or edit it.']},
   {field:'Achievement',meaning:['صافي المبيعات في النطاق ÷ الهدف × 100. للمندوب البسط هو مبيعاته هو، والمقام هدف فريقه المتاح، مش هدف شخصي جديد.','Net sales in scope ÷ target × 100. A salesperson’s numerator is their own sales; the denominator is the accessible team target, not a separate personal goal.']},
  ],
  example:{title:['ليه أهداف المنطقة والفروع مش بتتكرر؟','Why parent and branch targets are not doubled'],headers:[['المستوى','Level'],['الهدف','Target'],['طريقة العرض','Display']],rows:[
   [['منطقة الرياض','Riyadh region'],'100,000',['الهدف على مستوى المنطقة','Region-level target']],
   [['فرع أ','Branch A'],'30,000',['هدف الفرع عند اختياره','Used when selecting the branch']],
   [['فرع ب','Branch B'],'50,000',['هدف الفرع عند اختياره','Used when selecting the branch']],
   [['All accessible teams وفيها المنطقة','All accessible teams including the parent'],'100,000',['مش 180,000','Not 180,000']],
  ],note:['لو المندوب في فرع أ حقق 20,000، يعرض 66.7% مقابل هدف الفرع 30,000. ده لا يوقف عمولته ولا يغير نسبتها.','A salesperson contributing 20,000 to Branch A sees 66.7% against 30,000. This neither blocks nor changes their commission.']},
  questions:[
   {q:['لو الفرع ملوش هدف والمنطقة ليها؟','What if only the parent has a target?'],a:['هدف المنطقة يظهر في عرض المنطقة. اختيار فرع بعينه يستخدم الهدف المسجل للفرع نفسه؛ مفيش توزيع تلقائي لهدف الأب. سجل هدف الفرع لو محتاج مقارنة على مستواه.','The parent target appears at parent scope. Selecting a specific branch uses that branch’s own target; there is no automatic parent allocation. Create a branch target for a branch-level comparison.']},
   {q:['مين يقدر يشوف الأهداف ويعدلها؟','Who can view or edit targets?'],a:['المندوب يشوف أهداف الفرق اللي عضو فيها، والمدير كمان أهداف الفرق اللي بيقودها أو مسندة له وفروعها. التعديل لمسؤول العمولات، وكل ده داخل الشركات المسموحة.','Salespeople read targets for teams they belong to. Managers additionally see targets within led/assigned team hierarchies. Only commission administrators edit them, within allowed companies.']},
  ],
 },
 rules:{
  fields:[
   {field:'Name / Active',meaning:['اسم واضح للقاعدة. إلغاء Active بيأرشفها من المطابقة الجديدة؛ العمولة القديمة تحتفظ بالقاعدة والنسبة.','Use a clear rule name. Disabling Active archives it from new matching; older commissions keep their captured rule and rate.']},
   {field:'Company / Salesperson',meaning:['قاعدة خاصة بشركة ومندوب. المندوب اللي بيتطابق هو مندوب أمر البيع المصدر، مش Team Leader ولا مدير المنطقة.','Rules belong to one company and salesperson. Matching uses the source sale-order salesperson, not the Team Leader or region manager.']},
   {field:'Kind / Product category',meaning:['اختار Product category للسلع، وحدد نفس Product Category بالضبط. قاعدة الأب مش بتتطبق تلقائيًا على تصنيفات فرعية.','For goods choose Product category and the exact category. Parent-category rules do not automatically inherit to children.']},
   {field:'Kind / Service category',meaning:['للمنتج Service اختار Service category من فئات commission. لازم Commission Category على الـProduct variant تكون نفس الفئة.','For Service products choose an existing commission Service category. The product variant’s Commission Category must match it.']},
   {field:'Commission %',meaning:['نسبة من 0 إلى 100 بأربع منازل عشرية. صفر نسبة مقصودة ومسموحة؛ مثال 7 يساوي 7%، مش 0.07.','A percentage from 0 to 100 with four decimal places. Zero is a valid intentional rate. Enter 7 for 7%, not 0.07.']},
   {field:'Date From / Date To',meaning:['فترة سريان شاملة الطرفين حسب تاريخ الفاتورة. Date To فاضي يعني مستمرة. ممنوع تداخل قواعد نشطة لنفس الشركة والمندوب والنوع والتصنيف.','Inclusive effective dates based on invoice date. Blank Date To means ongoing. Active rules for the same company/person/type/category cannot overlap.']},
  ],
  example:{title:['تغيير نسبة شهر جديد بدون تغيير الماضي','Change a new month without rewriting history'],headers:[['القاعدة','Rule'],['الفترة','Dates'],['النسبة','Rate']],rows:[
   [['أحمد / أفلام','Ahmed / Film'],['01/10 إلى 31/10','01/10 through 31/10'],'10%'],
   [['أحمد / أفلام','Ahmed / Film'],['من 01/11، بدون نهاية','From 01/11, no end date'],'12%'],
   [['أحمد / خدمة VIP','Ahmed / VIP service'],['من 01/10','From 01/10'],'7%'],
  ],note:['فاتورة أكتوبر للمنتج صافيها 1,800 تستحق 180. فاتورة نوفمبر بنفس الصافي تستحق 216. مرتجع أكتوبر يفضل مربوط بنسبة 10%.','An October product invoice of 1,800 earns 180. A November invoice of the same net earns 216. A refund linked to October keeps the 10% original rate.']},
  questions:[
   {q:['ليه النظام بيرفض حفظ القاعدة؟','Why does saving a rule fail?'],a:['راجع النسبة والتواريخ، واختار فئة واحدة مطابقة للنوع. لو فيه قاعدة مفتوحة لنفس المندوب والفئة، اقفل Date To أو أرشفها قبل قاعدة جديدة متداخلة.','Check rate, dates and exactly one category matching the type. End-date or archive an existing open rule before creating an overlapping replacement.']},
   {q:['لو غيرت النسبة بعد ترحيل الفاتورة؟','What if a rate changes after posting?'],a:['العمولات المحسوبة مش بتتغير. إعادة محاولة Needs review فقط تستخدم الإعداد المصحح، أما reset وإعادة ترحيل الفاتورة فده مسار محاسبي كامل بيعيد حسابها.','Calculated snapshots stay unchanged. Retrying Needs review uses corrected setup. Resetting and reposting the invoice is a separate accounting workflow that recalculates it.']},
   {q:['ينفع أختار منتج Service في قاعدة Product category؟','Can a Service product use a Product category rule?'],a:['حساب الخدمة بيستخدم Service category الخاصة بها. إعداد قاعدة نوعها Product category مش بديل عن فئة الخدمة. راجع النوع والتصنيف على المنتج المصدر.','Services match their Service category. A Product category rule does not replace service classification. Verify the source product type and assigned category.']},
  ],
 },
 regions:{
  fields:[
   {field:'Sales Team / Company',meaning:['اسم الفريق والشركة. تقدر تستخدم فرق المبيعات الموجودة؛ مش مطلوب تعيد إنشاء فريق عشان العمولة. الفرق المشتركة بدون شركة تفضل خاضعة لشركة سطور العمولة المسموحة.','Use an existing sales team and company; duplicate teams are unnecessary. Shared teams without a company still respect commission-line company isolation.']},
   {field:'Commission Level / Parent region',meaning:['Region ثم Subregion ثم Branch. الأب لازم أعلى مستوى ومن نفس الشركة؛ ممكن تتخطى مستوى وسيط. ممنوع الدوائر أو تعارض مستوى الأبناء الحاليين.','Region → Subregion → Branch. Parent must be a higher level in the same company; an intermediate level may be skipped. Cycles and conflicts with existing children are rejected.']},
   {field:'Team Leader',meaning:['مصدر النطاق التلقائي: مدير المنطقة بياخد الفريق اللي هو قائده، وأي فرق تحته في Parent region. تغيير القائد يلغي نطاق القائد القديم فورًا، إلا لو له إسناد إضافي مستقل.','Automatic scope source: a region manager receives led teams and their Parent region descendants. Changing the leader immediately removes the old leader’s scope unless a separate additional assignment remains.']},
   {field:'Commission manager',meaning:['اختياري لإضافة مسؤول عمولات آخر غير القائد. مش مطلوب لو Team Leader هو المدير المقصود. إضافة مدير هنا لا تغير Team Leader، والاتنين ممكن يشوفوا النطاق لو لكل واحد دور Region manager.','Optional additional commission manager beyond the leader. Leave it empty when the leader is the intended manager. It does not change Team Leader; both may see the scope if each has the Region manager role.']},
   {field:'Salespersons',meaning:['أعضاء الفريق. العضوية بتفيد عرض هدف الفريق للمندوب؛ العضوية لوحدها لا تسمح بقراءة عمولات الزملاء.','Team members. Membership supports the salesperson’s team-target view; it alone never permits reading colleagues’ commissions.']},
  ],
  example:{title:['مثال النطاق التلقائي بدون إدخال يدوي','Automatic scope without manual assignment'],headers:[['الفريق','Team'],['الأب','Parent'],['القائد','Leader']],rows:[
   [['الرياض','Riyadh'],'—',['محمد','Mohamed']],
   [['الرياض شمال','Riyadh North'],['الرياض','Riyadh'],['سامي','Sami']],
   [['فرع 1','Branch 1'],['الرياض شمال','Riyadh North'],'—'],
   [['جدة','Jeddah'],'—',['خالد','Khaled']],
  ],note:['محمد + دور Region manager: يشوف الرياض والرياض شمال وفرع 1 تلقائيًا، ومش محتاج يملأ Additional managed regions. سامي يشوف الرياض شمال وفرع 1. جدة خارج نطاقهم.','Mohamed with Region manager sees Riyadh, Riyadh North and Branch 1 automatically, without Additional managed regions. Sami sees Riyadh North and Branch 1. Jeddah is outside their scopes.']},
  questions:[
   {q:['ليه Team Leader مش كفاية لوحده لدخول التطبيق؟','Why does Team Leader alone not open the app?'],a:['القائد بيحدد نطاق البيانات، لكن دور Commission Access هو اللي يسمح بدخول التطبيق. ده يمنع أي قائد مبيعات من اكتساب بيانات عمولات بدون منح الدور المقصود.','Leadership determines scope; Commission Access grants app access. A sales leader does not gain commission data until explicitly assigned the appropriate role.']},
   {q:['لو غيرت Team Leader أو نقلت فرع؟','What if leadership or parent team changes?'],a:['نطاق القراءة بيتحدث فورًا في السيرفر. اعمل Refresh للشاشة عشان الأرقام الحالية تتحدث. تعيين مدير إضافي مستقل بيظل فعالًا لحد حذفه. تغيير القيادة لا يعيد كتابة عمولات الفواتير القديمة أو مندوبها.','Server read scope updates immediately; refresh the screen for fresh totals. Separate additional manager assignments remain until removed. Leadership changes do not rewrite invoice commissions or attribution.']},
   {q:['هل المدير بياخد عمولة تلقائي من مبيعات فريقه؟','Does a manager automatically earn commission on team sales?'],a:['لا؛ قيادة الفريق تمنح الاطلاع فقط. استحقاق العمولة للمندوب المنسوب له أمر البيع حسب قاعدته. مفيش نسبة إدارية إضافية تلقائية في الموديول.','No. Leadership grants visibility only. Commission belongs to the source sale-order salesperson under their rule. The module adds no automatic management override commission.']},
  ],
 },
 categories:{
  fields:[
   {field:'Name',meaning:['اسم فئة الخدمة، زي VIP أو Platinum. دي نفس فئات موديول commission الموجود، مش جدول منفصل جديد لعمولات المبيعات.','Service category name, such as VIP or Platinum. This reuses existing commission-module categories rather than a separate sales-only catalog.']},
   {field:'Product type',meaning:['المنتج لازم نوعه Service علشان يستخدم مسار فئة الخدمة في حساب العمولة. السلع تستخدم Product Category.','The product must be Service to match service-category commission rules. Goods use Product Category instead.']},
   {field:'Commission Category on product variant',meaning:['اختار الفئة على الصنف/الـvariant من الحقل الموجود. مجرد كتابة VIP في اسم المنتج مش كفاية. لو فيه Variants، راجع كل variant مباع.','Assign the existing variant field. Putting VIP in a product name is insufficient. Review each sold variant when variants exist.']},
   {field:'Rule → Service category',meaning:['اختار نفس الفئة في قاعدة المندوب. الفئة لوحدها مش فيها نسبة للموديول ده؛ النسبة في Commission rules لكل مندوب وفترة.','Use the same category on the salesperson’s rule. The category alone does not supply this module’s rate; Commission rules defines it per person and period.']},
  ],
  example:{title:['نفس الفئة ونسب مختلفة حسب المندوب','One category, different salesperson rates'],headers:[['الخدمة','Service'],['المندوب','Salesperson'],['الصافي','Net'],['النسبة / العمولة','Rate / commission']],rows:[
   [['تركيب VIP','VIP installation'],['أحمد','Ahmed'],'1,000','7% / 70'],
   [['تركيب VIP','VIP installation'],['منى','Mona'],'1,000','5% / 50'],
  ],note:['الفئة في الحالتين VIP؛ كل مندوب له قاعدته الخاصة. التصنيف لا يخلط سجل عمولات المبيعات مع تسويات الفنيين القديمة.','Both products use VIP, but each salesperson has their own rule. Classification does not merge the sales ledger with existing technician settlements.']},
  questions:[
   {q:['لو الخدمة من غير فئة أو قاعدة؟','What if the service has no category or rule?'],a:['الفاتورة تترحل عادي لكن العمولة تتسجل Needs review بقيمة صفر. أصلح الفئة والقاعدة بتواريخ مناسبة، وبعدها Retry review من المعالج.','The invoice can post, but commission is recorded as Needs review at zero. Correct classification and dated rules, then Retry review in the wizard.']},
   {q:['هل تعديل الفئة يغير عمولات قديمة؟','Will editing a category change old commissions?'],a:['العمولات المحسوبة محتفظة باسم الفئة والنسبة وقت الحساب. التغيير يؤثر على الحسابات الجديدة والسطور المعاد تجربتها بعد المراجعة، مش الـSnapshots المحسوبة.','Calculated entries preserve category labels and rates. Changes affect new calculations and retried review rows, not calculated snapshots.']},
  ],
 },
 access:{
  fields:[
   {field:'Commission role',meaning:['دور واحد من أربعة. No commission access يمنع التطبيق؛ Salesperson لعمولاته فقط؛ Region manager لنفسه ونطاقه؛ Commission administrator لكل العمولات والإعدادات المسموحة بشركاته.','Choose one of four roles: No access; Salesperson for own entries; Region manager for own entries plus scope; Commission administrator for permitted-company commissions and configuration.']},
   {field:'Automatic teams from Team Leader',meaning:['عرض تلقائي للفرق اللي المستخدم قائد عليها. للقراءة فقط؛ مش مطلوب تختارها هنا ولا تنسخها يدويًا. غير Team Leader من فريق المبيعات نفسه. فرق الأبناء مضافة للنطاق بدون تكرار كل فرع في التاب.','Read-only preview of teams the user leads. No selection or manual copying is needed. Change Team Leader on the sales team itself. Descendants are included without listing every branch here.']},
   {field:'Additional managed regions / teams',meaning:['اختياري لو محتاج تضيف نطاق غير قيادة المبيعات. اختيار فريق مرتبط بمدير عمولة إضافي آخر ينقل الإسناد الإضافي فقط؛ قيادة المبيعات لا تتغير.','Optional scope beyond sales leadership. Selecting a team already assigned to another explicit commission manager transfers that additional assignment only; leadership is unchanged.']},
   {field:'Allowed Companies / Default Company',meaning:['من Access Rights الأساسية. الشركة الحالية تحدد أرقام الـDashboard، والشركات المسموحة تحد الوصول للسجل. إسناد فريق من شركة غير مسموحة مرفوض.','Managed in ordinary Access Rights. Current company controls dashboard totals; allowed companies bound ledger access. Additional assignments outside permitted companies are rejected.']},
   {field:'Historical accrual booking',meaning:['مؤشر للقراءة فقط. Yes عند الجمع بين Commission administrator وAccounting administrator. لا يمنح صلاحية حسابات، ولا يقوم بإثبات أو صرف عمولة بمجرد ظهوره.','Read-only eligibility indicator. True requires both Commission Administrator and Accounting Administrator. It neither grants accounting rights nor books or pays anything by itself.']},
   {field:'Guide / Open screen',meaning:['كل مستخدمي التطبيق يقدروا يقرأوا الشرح الكامل والأمثلة التجريبية. فتح الشاشات الإدارية يظل حسب صلاحيتهم؛ إتاحة الشرح لا تكشف سجلات حقيقية.','All app users can read the full handbook and fictional examples. Opening administrative screens remains permission-controlled; handbook access exposes no live records.']},
  ],
  example:{title:['مقارنة الأدوار عمليًا','Roles in practice'],headers:[['الدور','Role'],['بيانات العمولة','Commission data'],['التعديل','Editing']],rows:[
   [['بدون صلاحية','No access'],['لا دخول للتطبيق','No app access'],['لا شيء','None']],
   [['مندوب','Salesperson'],['عمولاته فقط، حتى لو قائد فريق','Own entries, even if a team leader'],['قراءة فقط','Read only']],
   [['مدير منطقة','Region manager'],['نفسه + الفرق بقيادته + النطاق الإضافي وفروعهم','Own + led + additional team hierarchies'],['قراءة فقط','Read only']],
   [['مسؤول عمولات','Commission administrator'],['كل ما تسمح به شركاته','All within allowed companies'],['قواعد وأهداف ومناطق؛ السجل لا يعدل يدويًا','Rules, goals and regions; ledger remains immutable']],
  ],note:['إدارة تاب المستخدمين تحتاج Administration / Settings. فتح الحسابات وإثبات القيود له صلاحيات محاسبية منفصلة. صلاحية المدير لا تحول عمولات الفريق إلى مستحقات شخصية له.','User-tab administration requires Settings access. Accounting and accrual booking need separate accounting permissions. Manager visibility does not turn team commission into the manager’s own entitlement.']},
  questions:[
   {q:['أنا بالفعل Team Leader، أعمل إيه بالضبط؟','I am already Team Leader. What exactly is needed?'],a:['مسؤول النظام يختار لك Region manager من Commission Access ويحفظ. الفرق اللي أنت قائدها تظهر تلقائيًا في Automatic teams، وفروعها تدخل نطاقك. سيب Additional managed regions فاضية إلا لو عايز نطاق زيادة.','A system administrator selects Region manager in Commission Access and saves. Led teams appear automatically and their descendants enter your scope. Leave Additional managed regions empty unless extra scope is required.']},
   {q:['إزالة المنطقة يدويًا هتمنع مديرها الأساسي؟','Does clearing an additional region revoke its leader?'],a:['لا؛ القيادة والإسناد الإضافي مصدرين مستقلين. لو المستخدم ما زال Team Leader، نطاقه التلقائي يفضل. لإلغاء وصوله الإقليمي كله غيّر دوره إلى Salesperson أو No access، أو انقل القيادة واحذف أي إسناد إضافي له.','No. Leadership and additional assignments are independent. A remaining Team Leader keeps automatic scope. To revoke all regional access, downgrade the role, or reassign leadership and remove additional assignments.']},
   {q:['ليه التطبيق مش ظاهر بعد التثبيت؟','Why is the app hidden after installation?'],a:['الموديول لا يمنح أدوارًا لكل المستخدمين تلقائيًا. افتح المستخدم الصحيح وحدد دور العمولة ثم احفظ واعمل Refresh. إعداد Team Leader لا يغني عن منح الدور.','Installation does not automatically grant everyone a role. Assign the intended user’s commission role, save and refresh. Team Leader does not replace the role assignment.']},
   {q:['هل نفس الحدود بتطبق على التصدير والـPivot؟','Do these limits apply to exports and pivots?'],a:['نعم؛ الوصول بيتطبق بقواعد السيرفر على السجل والتصدير والـPivot والـDashboard، مش بإخفاء أزرار بس. المندوب لا يقدر يرفع دوره أو يعين نفسه قائد فريق بصلاحية العمولة العادية.','Yes. Server rules govern ledger reads, exports, pivots and dashboard aggregates. This is not merely button hiding. Ordinary commission users cannot elevate their role or assign themselves team leadership.']},
  ],
 },
 accounting:{
  fields:[
   {field:'Recognize commission liabilities',meaning:['تفعيل اختياري لكل شركة، افتراضيًا متوقف. عند تشغيله، ترحيل فاتورة جديدة بعمولة محسوبة غير صفرية ينشئ قيد استحقاق تلقائي.','Optional per-company switch, off by default. When enabled, a newly posted invoice with nonzero calculated commission generates an accrual.']},
   {field:'Commission journal',meaning:['يومية Miscellaneous نشطة من نفس الشركة وبعملة الشركة أو بدون عملة خاصة. ليست يومية بيع أو بنك.','An active miscellaneous journal in the same company, with company currency or no forced currency. Not a sales or bank journal.']},
   {field:'Commission expense (Debit)',meaning:['حساب مصروف نشط من نفس الشركة، بعملة الشركة أو بدون تقييد عملة. ده الجانب المدين لقيد استحقاق الفاتورة.','An active expense account in the same company, using company currency or no forced currency. This is the invoice accrual debit.']},
   {field:'Commission payable (Credit)',meaning:['حساب التزام/مستحق مختلف عن المصروف. لو نوعه Payable، سطور القيد تحتفظ بشريك المندوب لإجراءات التسوية المعتادة.','A distinct liability/payable account. With a payable account, journal lines retain the salesperson’s partner for normal reconciliation.']},
   {field:'Book commission accrual',meaning:['في سطر السجل التاريخي Not booked؛ يحتاج دوري Commission administrator وAccounting administrator، وتفعيل الإعدادات للأصل. راجع تاريخ المستند والفترات المقفولة قبل الإثبات.','On historical Not booked ledger rows. Requires both administrator roles and enabled accrual settings for the original. Check document dates and accounting locks before booking.']},
   {field:'Commission accounting on invoice',meaning:['تاب لمستخدم الحسابات بيحفظ رابط القيود والعكوس، حالتها ويوميتها. السجل كمان فيه رابط القيد. لا يتم إنشاء دفعة أو كشف مرتبات.','An accounting-user invoice tab preserves accrual and reversal links, state and journal. The ledger also links the entry. No payment or payroll run is created.']},
  ],
  example:{title:['قيود مثال عمولة 250 ومرتجع 45','Journal example: commission 250, refund 45'],headers:[['الحركة','Movement'],['الحساب','Account'],['مدين','Debit'],['دائن','Credit']],rows:[
   [['إثبات الفاتورة','Invoice accrual'],['مصروف عمولات','Commission expense'],'250','0'],
   [['إثبات الفاتورة','Invoice accrual'],['مستحق عمولات','Commission payable'],'0','250'],
   [['عكس عمولة المرتجع','Refund commission reversal'],['مستحق عمولات','Commission payable'],'45','0'],
   [['عكس عمولة المرتجع','Refund commission reversal'],['مصروف عمولات','Commission expense'],'0','45'],
  ],note:['صافي الالتزام 205. القيد إثبات الاستحقاق فقط؛ دفع المبلغ للمندوب وتسويته تتم من إجراءات الحسابات المعتادة. أي أرقام أو أسماء حسابات هنا أمثلة وليست إعدادًا مفروضًا.','Net liability is 205. These entries recognize entitlement only; payment and reconciliation follow normal accounting procedures. Amounts and account names are illustrative, not mandated configuration.']},
  questions:[
   {q:['لو غيرت الحسابات أو قفلت التفعيل بعد الفاتورة؟','What if settings change after an invoice?'],a:['مرتجع عمولة مثبتة يرجع لنفس اليومية والحسابات الأصلية المحفوظة، حتى بعد تغيير الإعدادات أو إيقاف الإثبات الجديد. عمولة أصل غير مثبتة لا تنشئ التزامًا سالبًا من المرتجع وحده.','Refunds of booked commission use original journal/account snapshots, even after settings change or new accruals are disabled. An unbooked original cannot generate a negative liability from a refund alone.']},
   {q:['أقدر أعدل القيد أو أرجعه مسودة مباشرة؟','Can generated accruals be edited or reset directly?'],a:['القيود المولدة محمية من التعديل والحذف والعكس اليدوي. استخدم مسار الفاتورة المصدر. القفل المالي والتحقق المحاسبي الطبيعيين يفضلوا شغالين، وأي فشل يتراجع بالعملية كاملة.','Generated accruals are protected from manual edits, deletion and reversal. Use the source invoice workflow. Normal accounting locks/validation apply, and failures roll back the operation.']},
   {q:['ليه الفاتورة ممكن تترفض عند الترحيل؟','Why might posting fail?'],a:['نقص قاعدة العمولة يحولها Needs review من غير منع الترحيل. لكن لو الإثبات المحاسبي مفعل وإعداد الحسابات أو اليومية غير صالح، خطأ القيود ممكن يمنع العملية؛ صحح الإعدادات قبل إعادة المحاولة.','A missing commission rule produces Needs review without blocking posting. When accruals are enabled, invalid accounting setup can block the transaction; correct accounts/journal before retrying.']},
  ],
 },
 calculate:{
  fields:[
   {field:'Company',meaning:['الشركة المطلوب معالجة فواتيرها. لازم تكون ضمن الشركات المسموحة للمسؤول؛ كل دفعة لشركة واحدة.','The company whose invoices will be processed. It must be allowed for the administrator; each batch handles one company.']},
   {field:'Date From / Date To',meaning:['فترة شاملة حسب تاريخ الفاتورة المستخدم في العمولة. النظام يعالج فواتير العملاء والمرتجعات Posted فقط. الحد 500 مستند في الدفعة، فصغر الفترة عند الحاجة.','Inclusive commission-date range. Only posted customer invoices and credit notes are processed. The batch limit is 500 documents; narrow the dates when needed.']},
   {field:'Retry entries needing review',meaning:['لو مفعلة، يعيد تجربة السطور Needs review بعد تصحيح السبب. السطور المحسوبة سابقًا مش بيغير نسبها أو قيمها.','Retries Needs review rows after corrections. Already calculated rows keep their captured rates and amounts.']},
   {field:'Calculate',meaning:['ينشئ السطور الناقصة ويجرب سطور المراجعة المختارة. الفواتير الأصلية بتتعالج قبل المرتجعات داخل نفس الدفعة، وبعدها تقدر تراجع النتائج في السجل.','Creates missing rows and retries selected review rows. Original invoices precede credits within a batch; inspect the resulting ledger afterwards.']},
   {field:'Book commission accrual',meaning:['خطوة منفصلة من السجل بعد التأكد من الحساب. المعالج لا ينشئ قيودًا تاريخية ولا مدفوعات تلقائيًا.','A separate ledger step after validating calculations. The wizard does not silently create historical journal entries or payments.']},
  ],
  example:{title:['تصحيح قاعدة ناقصة على فاتورة قديمة','Resolve an older invoice with a missing rule'],headers:[['الخطوة','Step'],['النتيجة','Result']],rows:[
   [['فاتورة قديمة صافيها 1,800 بدون قاعدة','Older net invoice 1,800 with no rule'],['Needs review / عمولة صفر','Needs review / zero commission']],
   [['إنشاء قاعدة 10% تغطي تاريخها','Create a dated 10% rule covering it'],['تجهيز الإعداد فقط','Setup corrected only']],
   [['تشغيل Calculate مع Retry review','Run Calculate with Retry review'],['Calculated / 180 / Not booked','Calculated / 180 / Not booked']],
   [['مسؤول مؤهل يختار Book commission accrual','Eligible administrator selects Book commission accrual'],['قيد استحقاق 180 حسب الإعدادات','Accrual entry 180 under configured accounts']],
  ],note:['إعادة تشغيل Calculate مرة أخرى لا تكرر سطر الـSnapshot ولا تعيد تسعير العمولة المحسوبة. استخدم نسخة QA لمراجعة عينة قبل معالجة نطاق تاريخي كبير.','Running Calculate again does not duplicate snapshots or reprice calculated commission. Review a QA sample before processing a large historical range.']},
  questions:[
   {q:['لو المرتجع في شهر غير شهر الفاتورة؟','What if the refund is in a later month?'],a:['احسب فترة الفواتير الأصلية الأول، وبعدها فترة المرتجعات، علشان العمولة الأصلية تكون موجودة للربط. المعالج يرتب الأصل قبل المرتجع داخل الدفعة نفسها فقط.','Process original-invoice periods first, then refund periods, so original commissions exist for linking. The wizard orders originals before refunds within each batch.']},
   {q:['لو Needs review فضل موجود؟','What if Needs review remains?'],a:['افتح Note بالسجل. راجع أصل أمر البيع والمندوب والفريق والشركة، وتصنيف المنتج والقاعدة المؤرخة. المرتجع الغامض يحتاج أصلًا فريدًا؛ إضافة نسبة وحدها لا تصلح ربطًا غامضًا.','Read the ledger Note. Check source sale order, salesperson, team, company, product category and dated rule. Ambiguous refunds need a unique original; adding a rate alone does not fix attribution.']},
   {q:['هل التثبيت أو Upgrade يعالج القديم تلقائي؟','Does installation or upgrade process history automatically?'],a:['لا. التثبيت والتحديث يحافظوا على البيانات الموجودة ولا يشغلوا backfill للفواتير القديمة. المعالجة التاريخية وإثبات القيود خطوات صريحة للمسؤولين المصرح لهم.','No. Installation and upgrade preserve existing data and do not backfill historical invoices. Historical calculation and accrual booking are explicit authorized steps.']},
  ],
 },
};
