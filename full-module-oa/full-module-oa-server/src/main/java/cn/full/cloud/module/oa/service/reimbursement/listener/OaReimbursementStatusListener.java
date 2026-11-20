package cn.full.cloud.module.oa.service.reimbursement.listener;

import cn.full.cloud.module.bpm.api.event.BpmProcessInstanceStatusEvent;
import cn.full.cloud.module.bpm.api.event.BpmProcessInstanceStatusEventListener;
import cn.full.cloud.module.oa.enums.BpmModelConstants;
import cn.full.cloud.module.oa.service.reimbursement.OaReimbursementService;
import jakarta.annotation.Resource;
import cn.full.cloud.module.oa.enums.ApiConstants;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * 费用报销审批结果监听器
 *
 * @author 芋道源码
 */
@RestController
@Validated
public class OaReimbursementStatusListener extends BpmProcessInstanceStatusEventListener {

    @Resource
    private OaReimbursementService reimbursementService;

    @Override
    public String getProcessDefinitionKey() {
        return BpmModelConstants.REIMBURSEMENT;
    }

    @Override
    @PostMapping(ApiConstants.PREFIX + "/reimbursement/update-audit-status") // 提供给 bpm-server RPC 调用
    protected void onEvent(@RequestBody BpmProcessInstanceStatusEvent event) {
        reimbursementService.updateReimbursementStatus(Long.valueOf(event.getBusinessKey()), event.getStatus());
    }

}
