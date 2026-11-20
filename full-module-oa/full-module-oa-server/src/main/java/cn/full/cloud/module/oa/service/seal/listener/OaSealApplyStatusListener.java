package cn.full.cloud.module.oa.service.seal.listener;

import cn.full.cloud.module.bpm.api.event.BpmProcessInstanceStatusEvent;
import cn.full.cloud.module.bpm.api.event.BpmProcessInstanceStatusEventListener;
import cn.full.cloud.module.oa.enums.BpmModelConstants;
import cn.full.cloud.module.oa.service.seal.OaSealApplyService;
import jakarta.annotation.Resource;
import cn.full.cloud.module.oa.enums.ApiConstants;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * 用印申请审批结果监听器
 *
 * @author 芋道源码
 */
@RestController
@Validated
public class OaSealApplyStatusListener extends BpmProcessInstanceStatusEventListener {

    @Resource
    private OaSealApplyService sealApplyService;

    @Override
    public String getProcessDefinitionKey() {
        return BpmModelConstants.SEAL_APPLY;
    }

    @Override
    @PostMapping(ApiConstants.PREFIX + "/seal-apply/update-audit-status") // 提供给 bpm-server RPC 调用
    protected void onEvent(@RequestBody BpmProcessInstanceStatusEvent event) {
        sealApplyService.updateSealApplyStatus(Long.parseLong(event.getBusinessKey()), event.getStatus());
    }

}
