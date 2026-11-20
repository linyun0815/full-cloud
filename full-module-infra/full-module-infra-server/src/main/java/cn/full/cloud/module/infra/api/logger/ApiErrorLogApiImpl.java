package cn.full.cloud.module.infra.api.logger;

import cn.full.cloud.framework.common.biz.infra.logger.ApiErrorLogCommonApi;
import cn.full.cloud.framework.common.biz.infra.logger.dto.ApiErrorLogCreateReqDTO;
import cn.full.cloud.framework.common.pojo.CommonResult;
import cn.full.cloud.module.infra.service.logger.ApiErrorLogService;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.RestController;

import jakarta.annotation.Resource;

import static cn.full.cloud.framework.common.pojo.CommonResult.success;

@RestController // 提供 RESTful API 接口，给 Feign 调用
@Validated
public class ApiErrorLogApiImpl implements ApiErrorLogCommonApi {

    @Resource
    private ApiErrorLogService apiErrorLogService;

    @Override
    public CommonResult<Boolean> createApiErrorLog(ApiErrorLogCreateReqDTO createDTO) {
        apiErrorLogService.createApiErrorLog(createDTO);
        return success(true);
    }

}
